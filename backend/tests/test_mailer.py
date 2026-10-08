import ssl
from typing import ClassVar

from app.core.config import Settings
from app.modules.notify import mailer as mailer_mod
from app.modules.notify.mailer import SmtpMailer


class _FakeSMTP:
    instances: ClassVar[list["_FakeSMTP"]] = []

    def __init__(self, host, port, timeout):
        self.calls: list[tuple] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append(("starttls", context))

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, msg):
        self.calls.append(("send", msg["To"]))


async def test_starttls_verifies_server_certificate_before_login(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mailer_mod.smtplib, "SMTP", _FakeSMTP)
    s = Settings(_env_file=None, smtp_starttls=True, smtp_user="u", smtp_password="p")
    await SmtpMailer(s).send("a@x.com", "S", "T", "<p>T</p>")
    (smtp,) = _FakeSMTP.instances
    kind, context = smtp.calls[0]
    assert kind == "starttls"
    assert isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_REQUIRED
    assert [c[0] for c in smtp.calls] == ["starttls", "login", "send"]

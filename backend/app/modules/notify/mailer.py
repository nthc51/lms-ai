import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.core.config import Settings


class Mailer(Protocol):
    async def send(self, to: str, subject: str, text: str, html: str) -> None: ...


class SmtpMailer:
    """SMTP chuẩn (Mailpit khi dev, Brevo khi chạy thật). smtplib chạy trong thread để không chặn event loop."""

    def __init__(self, s: Settings):
        self.s = s

    def _send_sync(self, msg: EmailMessage) -> None:
        s = self.s
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_s) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)

    async def send(self, to: str, subject: str, text: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.s.mail_from
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="lms-ai")
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        await asyncio.to_thread(self._send_sync, msg)

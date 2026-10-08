from app.core.storage import download_headers


class InMemoryStorage:
    """Storage giả trong bộ nhớ. Test đóng vai trình duyệt PUT bằng `client_put` vào đúng key của URL presign."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.mimes: dict[str, str] = {}
        self.signed_gets: dict[str, dict[str, str]] = {}  # key -> header response đã được yêu cầu ký
        self.on_copy = None  # hook chạy ngay trước khi copy, để mô phỏng client PUT chen vào giữa chừng

    def client_put(self, put_url: str, data: bytes, mime: str = "application/octet-stream") -> str:
        key = put_url.removeprefix("memory://put/")
        self.objects[key] = data
        self.mimes[key] = mime
        return key

    async def presign_put(self, key, expires_s=900):
        return f"memory://put/{key}"

    async def presign_get(self, key, mime, expires_s=3600, download_name=None):
        self.signed_gets[key] = download_headers(mime, download_name)
        return f"memory://get/{key}"

    async def stat_size(self, key):
        data = self.objects.get(key)
        return None if data is None else len(data)

    async def read_head(self, key, n=2048):
        return self.objects[key][:n]

    async def read_all(self, key):
        return self.objects[key]

    async def put(self, key, data, mime):
        self.objects[key] = data
        self.mimes[key] = mime

    async def copy(self, src_key, dst_key):
        if self.on_copy is not None:
            self.on_copy()
        self.objects[dst_key] = self.objects[src_key]
        if src_key in self.mimes:
            self.mimes[dst_key] = self.mimes[src_key]

    async def remove(self, key):
        self.objects.pop(key, None)
        self.mimes.pop(key, None)


class RecordingQueue:
    """Queue giả. Kiểm tra luôn luật 'job phải được commit trước khi enqueue'."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, object]] = []

    async def enqueue(self, job) -> None:
        from app.core.db import SessionLocal
        from app.modules.jobs.models import Job

        async with SessionLocal() as s:
            assert await s.get(Job, job.id) is not None, "Job phải được commit trước khi enqueue"
        self.jobs.append((job.type, job.ref_id))


class InMemoryRateLimiter:
    """Rate limiter giả trong bộ nhớ, không có thời gian: vượt giới hạn thì luôn trả cả cửa sổ."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def hit(self, key: str, limit: int, window_s: int) -> int | None:
        self.counts[key] = self.counts.get(key, 0) + 1
        return window_s if self.counts[key] > limit else None


class RecordingKicker:
    """MailKicker giả: chỉ đếm số lần API báo worker gửi email."""

    def __init__(self) -> None:
        self.kicks = 0

    async def kick(self) -> None:
        self.kicks += 1


class RecordingMailer:
    """Mailer giả cho send_pending: ghi lại email đã gửi; fail_times > 0 thì ném lỗi N lần đầu."""

    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[dict] = []
        self.fail_times = fail_times

    async def send(self, to: str, subject: str, text: str, html: str) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("SMTP down")
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})

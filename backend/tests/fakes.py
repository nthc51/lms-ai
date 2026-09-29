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

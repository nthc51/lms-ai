import asyncio
import io
from datetime import timedelta
from functools import lru_cache
from typing import Protocol

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from app.core.config import Settings, get_settings

STAGING_PREFIX = "staging/"


def staging_key(key: str) -> str:
    """Key tạm mà trình duyệt được PUT vào. Key chính thức chỉ server ghi (copy sau khi kiểm tra)."""
    return STAGING_PREFIX + key


def download_headers(mime: str, download_name: str | None = None) -> dict[str, str]:
    """Header response ký kèm presigned GET: luôn trả đúng Content-Type, thêm attachment nếu có tên file."""
    headers = {"response-content-type": mime}
    if download_name:
        headers["response-content-disposition"] = f'attachment; filename="{download_name}"'
    return headers


class Storage(Protocol):
    async def presign_put(self, key: str, expires_s: int = 900) -> str: ...
    async def presign_get(self, key: str, mime: str, expires_s: int = 3600,
                          download_name: str | None = None) -> str: ...
    async def stat_size(self, key: str) -> int | None: ...
    async def read_head(self, key: str, n: int = 2048) -> bytes: ...
    async def read_all(self, key: str) -> bytes: ...
    async def put(self, key: str, data: bytes, mime: str) -> None: ...
    async def copy(self, src_key: str, dst_key: str) -> None: ...
    async def remove(self, key: str) -> None: ...


class MinioStorage:
    REGION = "us-east-1"  # có sẵn region thì client không cần gọi mạng để dò region khi ký URL

    def __init__(self, s: Settings):
        kw = dict(access_key=s.minio_access_key, secret_key=s.minio_secret_key,
                  secure=s.minio_secure, region=self.REGION)
        self._internal = Minio(s.minio_endpoint, **kw)       # API và worker gọi trong mạng Docker
        self._public = Minio(s.minio_public_endpoint, **kw)  # chỉ dùng để ký URL cho trình duyệt
        self._bucket = s.minio_bucket

    async def ensure_bucket(self) -> None:
        def run() -> None:
            if not self._internal.bucket_exists(self._bucket):
                self._internal.make_bucket(self._bucket)
        await asyncio.to_thread(run)

    async def presign_put(self, key: str, expires_s: int = 900) -> str:
        return await asyncio.to_thread(self._public.presigned_put_object, self._bucket, key,
                                       timedelta(seconds=expires_s))

    async def presign_get(self, key: str, mime: str, expires_s: int = 3600,
                          download_name: str | None = None) -> str:
        headers = download_headers(mime, download_name)
        return await asyncio.to_thread(lambda: self._public.presigned_get_object(
            self._bucket, key, expires=timedelta(seconds=expires_s), response_headers=headers))

    async def stat_size(self, key: str) -> int | None:
        def run() -> int | None:
            try:
                return self._internal.stat_object(self._bucket, key).size
            except S3Error as e:
                if e.code in ("NoSuchKey", "NoSuchObject"):
                    return None
                raise
        return await asyncio.to_thread(run)

    async def read_head(self, key: str, n: int = 2048) -> bytes:
        def run() -> bytes:
            resp = self._internal.get_object(self._bucket, key, offset=0, length=n)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        return await asyncio.to_thread(run)

    async def read_all(self, key: str) -> bytes:
        def run() -> bytes:
            resp = self._internal.get_object(self._bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        return await asyncio.to_thread(run)

    async def put(self, key: str, data: bytes, mime: str) -> None:
        await asyncio.to_thread(self._internal.put_object, self._bucket, key, io.BytesIO(data), len(data),
                                content_type=mime)

    async def copy(self, src_key: str, dst_key: str) -> None:
        # copy phía server, giữ nguyên metadata (Content-Type) của object nguồn
        await asyncio.to_thread(self._internal.copy_object, self._bucket, dst_key,
                                CopySource(self._bucket, src_key))

    async def remove(self, key: str) -> None:
        await asyncio.to_thread(self._internal.remove_object, self._bucket, key)


@lru_cache
def get_storage() -> Storage:
    return MinioStorage(get_settings())

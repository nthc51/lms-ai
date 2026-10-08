from urllib.parse import parse_qs, urlsplit

from app.core.config import Settings
from app.core.storage import MinioStorage, download_headers, staging_key

# Ký URL là tính toán cục bộ (region cố định), không cần MinIO chạy


def _storage() -> MinioStorage:
    return MinioStorage(Settings(minio_endpoint="minio:9000", minio_public_endpoint="files.example.com"))


def test_download_headers():
    assert download_headers("application/pdf") == {"response-content-type": "application/pdf"}
    assert download_headers("text/plain", "bai.txt") == {
        "response-content-type": "text/plain",
        "response-content-disposition": 'attachment; filename="bai.txt"',
    }
    # Tên tiếng Việt: tên ASCII dự phòng (đ → d) + filename* UTF-8 cho trình duyệt hiện đại
    assert download_headers("application/pdf", "Đề cương.pdf")["response-content-disposition"] == (
        "attachment; filename=\"De cuong.pdf\"; filename*=UTF-8''%C4%90%E1%BB%81%20c%C6%B0%C6%A1ng.pdf"
    )


async def test_presign_get_signs_public_host_with_content_type():
    url = await _storage().presign_get("video/u/a.mp4", "video/mp4")
    parts = urlsplit(url)
    assert parts.netloc == "files.example.com" and parts.path == "/lms/video/u/a.mp4"
    assert parse_qs(parts.query)["response-content-type"] == ["video/mp4"]


async def test_presign_put_targets_given_staging_key():
    url = await _storage().presign_put(staging_key("pdf/u/a.pdf"))
    parts = urlsplit(url)
    assert parts.netloc == "files.example.com" and parts.path == "/lms/staging/pdf/u/a.pdf"


class _RacingMinio:
    """bucket_exists nói chưa có, nhưng make_bucket thấy tiến trình khác (API/worker) vừa tạo xong."""

    def __init__(self, code: str):
        self.code = code

    def bucket_exists(self, bucket):
        return False

    def make_bucket(self, bucket):
        from minio.error import S3Error

        raise S3Error(None, self.code, "race", bucket, "req", "host", bucket_name=bucket)


async def test_ensure_bucket_tolerates_concurrent_creation():
    import pytest
    from minio.error import S3Error

    for code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
        s = _storage()
        s._internal = _RacingMinio(code)
        await s.ensure_bucket()  # không ném lỗi
    s = _storage()
    s._internal = _RacingMinio("AccessDenied")
    with pytest.raises(S3Error):
        await s.ensure_bucket()

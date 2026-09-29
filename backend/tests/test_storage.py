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
        "response-content-disposition": 'attachment; filename="bai.txt"'}


async def test_presign_get_signs_public_host_with_content_type():
    url = await _storage().presign_get("video/u/a.mp4", "video/mp4")
    parts = urlsplit(url)
    assert parts.netloc == "files.example.com" and parts.path == "/lms/video/u/a.mp4"
    assert parse_qs(parts.query)["response-content-type"] == ["video/mp4"]


async def test_presign_put_targets_given_staging_key():
    url = await _storage().presign_put(staging_key("pdf/u/a.pdf"))
    parts = urlsplit(url)
    assert parts.netloc == "files.example.com" and parts.path == "/lms/staging/pdf/u/a.pdf"

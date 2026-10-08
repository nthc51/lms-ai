async def test_api_responses_have_security_headers(client):
    r = await client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'none'" in r.headers["content-security-policy"]


async def test_error_responses_also_have_security_headers(client):
    r = await client.get("/api/v1/khong-ton-tai")
    assert r.status_code == 404
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_swagger_docs_are_not_blocked_by_api_csp(client):
    # Swagger UI tải JS/CSS từ CDN, nên CSP "default-src 'none'" sẽ làm trang trắng
    r = await client.get("/docs")
    assert r.status_code == 200
    assert "content-security-policy" not in r.headers

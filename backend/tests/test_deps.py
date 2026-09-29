import httpx
from fastapi import Depends

from app.core.deps import require_role, require_staff, require_teacher_approved
from app.main import create_app
from app.modules.auth.models import Role
from tests.helpers import make_admin, make_student, make_teacher


def _app_with_probe_routes():
    app = create_app()
    require_student = require_role(Role.student)

    @app.get("/probe/teacher")
    async def teacher_only(user=Depends(require_teacher_approved)):
        return {"ok": True}

    @app.get("/probe/staff")
    async def staff_only(user=Depends(require_staff)):
        return {"ok": True}

    @app.get("/probe/student")
    async def student_only(user=Depends(require_student)):
        return {"ok": True}

    return app


async def test_role_matrix(client):
    _, sv = await make_student(client)
    _, gv = await make_teacher(client)
    _, gv_pending = await make_teacher(client, "pending@x.com", approved=False)
    _, ad = await make_admin(client)

    app = _app_with_probe_routes()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:

        async def code(path, headers):
            r = await c.get(path, headers=headers)
            return r.status_code, (r.json().get("error") or {}).get("code")

        assert await code("/probe/teacher", gv) == (200, None)
        assert await code("/probe/teacher", gv_pending) == (403, "TEACHER_NOT_APPROVED")
        assert await code("/probe/teacher", sv) == (403, "FORBIDDEN")
        assert await code("/probe/staff", ad) == (200, None)
        assert await code("/probe/staff", gv) == (200, None)
        assert await code("/probe/staff", gv_pending) == (403, "TEACHER_NOT_APPROVED")
        assert await code("/probe/staff", sv) == (403, "FORBIDDEN")
        assert await code("/probe/student", sv) == (200, None)
        assert await code("/probe/student", gv) == (403, "FORBIDDEN")


async def test_approve_teacher_service(client, db):
    from app.modules.auth.service import approve_teacher

    uid, _ = await make_teacher(client, "later@x.com", approved=False)
    user = await approve_teacher(db, "later@x.com")
    assert str(user.id) == uid and user.teacher_status.value == "approved"

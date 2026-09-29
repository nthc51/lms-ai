"""Import mọi module models để Base.metadata có đủ bảng (dùng cho Alembic và test)."""

from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.courses import models as courses_models  # noqa: F401
from app.modules.enrollment import models as enrollment_models  # noqa: F401
from app.modules.materials import models as materials_models  # noqa: F401


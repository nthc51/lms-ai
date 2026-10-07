"""Import mọi module models để Base.metadata có đủ bảng (dùng cho Alembic và test)."""

from app.ai import models as ai_models  # noqa: F401
from app.modules.admin import models as admin_models  # noqa: F401
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.courses import models as courses_models  # noqa: F401
from app.modules.enrollment import models as enrollment_models  # noqa: F401
from app.modules.jobs import models as jobs_models  # noqa: F401
from app.modules.materials import models as materials_models  # noqa: F401
from app.modules.notify import models as notify_models  # noqa: F401
from app.modules.quiz import models as quiz_models  # noqa: F401
from app.modules.tutor import models as tutor_models  # noqa: F401

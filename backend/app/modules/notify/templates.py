"""Nội dung email. Mỗi hàm trả (subject, text, html). HTML tối giản, inline style để hiện ổn trong Gmail."""

from html import escape

Mail = tuple[str, str, str]


def _html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    body = "".join(f'<p style="margin:0 0 12px">{p}</p>' for p in paragraphs)
    if button:
        label, url = button
        body += (
            f'<p style="margin:20px 0"><a href="{escape(url)}" style="background:#0f766e;color:#fff;'
            f'padding:10px 18px;border-radius:6px;text-decoration:none;display:inline-block">{escape(label)}</a></p>'
            f'<p style="margin:0 0 12px;font-size:13px;color:#555">Nếu nút không bấm được, mở link: {escape(url)}</p>'
        )
    return (
        '<div style="font-family:Arial,sans-serif;font-size:15px;color:#111;max-width:560px;margin:auto">'
        f'<h2 style="font-size:20px">{escape(title)}</h2>{body}'
        '<p style="margin-top:24px;font-size:12px;color:#777">LMS-AI · Email tự động, vui lòng không trả lời.</p></div>'
    )


def verify_email(name: str, url: str, hours: int) -> Mail:
    subject = "Xác nhận email đăng ký LMS-AI"
    text = (
        f"Chào {name},\n\nBấm link sau để xác nhận email và kích hoạt tài khoản (hiệu lực {hours} giờ):\n{url}\n\n"
        "Nếu bạn không đăng ký, hãy bỏ qua email này."
    )
    html = _html(
        "Xác nhận email",
        [
            f"Chào {escape(name)},",
            f"Bấm nút dưới đây để kích hoạt tài khoản. Link có hiệu lực {hours} giờ.",
            "Nếu bạn không đăng ký, hãy bỏ qua email này.",
        ],
        ("Xác nhận email", url),
    )
    return subject, text, html


def teacher_approved(name: str, url: str) -> Mail:
    subject = "Tài khoản giảng viên đã được duyệt"
    text = f"Chào {name},\n\nTài khoản giảng viên của bạn đã được duyệt. Bạn có thể tạo khóa học ngay:\n{url}"
    html = _html(
        "Tài khoản đã được duyệt",
        [
            f"Chào {escape(name)},",
            "Tài khoản giảng viên của bạn đã được duyệt. Bạn có thể tạo khóa học ngay.",
        ],
        ("Tạo khóa học", url),
    )
    return subject, text, html


def teacher_rejected(name: str, reason: str, url: str) -> Mail:
    subject = "Yêu cầu giảng dạy chưa được chấp nhận"
    text = (
        f"Chào {name},\n\nYêu cầu giảng dạy của bạn chưa được chấp nhận.\nLý do: {reason}\n\n"
        f"Bạn có thể bổ sung thông tin và gửi lại yêu cầu tại:\n{url}"
    )
    html = _html(
        "Yêu cầu chưa được chấp nhận",
        [
            f"Chào {escape(name)},",
            "Yêu cầu giảng dạy của bạn chưa được chấp nhận.",
            f"<b>Lý do:</b> {escape(reason)}",
            "Bạn có thể bổ sung thông tin và gửi lại yêu cầu.",
        ],
        ("Gửi lại yêu cầu", url),
    )
    return subject, text, html


def account_locked(name: str, reason: str | None) -> Mail:
    subject = "Tài khoản LMS-AI đã bị khóa"
    why = f"Lý do: {reason}" if reason else "Liên hệ quản trị viên để biết thêm chi tiết."
    text = f"Chào {name},\n\nTài khoản của bạn đã bị quản trị viên khóa.\n{why}"
    html = _html(
        "Tài khoản đã bị khóa",
        [f"Chào {escape(name)},", "Tài khoản của bạn đã bị quản trị viên khóa.", escape(why)],
    )
    return subject, text, html


def course_hidden(name: str, title: str, reason: str, url: str) -> Mail:
    subject = f"Khóa học “{title}” đã bị ẩn"
    text = (
        f"Chào {name},\n\nQuản trị viên đã ẩn khóa học “{title}”.\nLý do: {reason}\n\n"
        f"Hãy chỉnh sửa nội dung rồi liên hệ quản trị viên để được hiện lại:\n{url}"
    )
    html = _html(
        "Khóa học đã bị ẩn",
        [
            f"Chào {escape(name)},",
            f"Quản trị viên đã ẩn khóa học <b>{escape(title)}</b>.",
            f"<b>Lý do:</b> {escape(reason)}",
            "Hãy chỉnh sửa nội dung rồi liên hệ quản trị viên để được hiện lại.",
        ],
        ("Mở trình soạn khóa", url),
    )
    return subject, text, html


def course_unhidden(name: str, title: str, url: str) -> Mail:
    subject = f"Khóa học “{title}” đã được hiện lại"
    text = f"Chào {name},\n\nKhóa học “{title}” đã được hiện lại, học viên học tiếp được.\n{url}"
    html = _html(
        "Khóa học đã được hiện lại",
        [
            f"Chào {escape(name)},",
            f"Khóa học <b>{escape(title)}</b> đã được hiện lại, học viên học tiếp được.",
        ],
        ("Mở khóa học", url),
    )
    return subject, text, html


def new_pending_teacher(teacher_name: str, teacher_email: str, url: str) -> Mail:
    subject = f"Giảng viên mới chờ duyệt: {teacher_name}"
    text = f"{teacher_name} ({teacher_email}) đang chờ duyệt tài khoản giảng viên.\n{url}"
    html = _html(
        "Giảng viên mới chờ duyệt",
        [f"<b>{escape(teacher_name)}</b> ({escape(teacher_email)}) đang chờ duyệt tài khoản giảng viên."],
        ("Mở danh sách chờ duyệt", url),
    )
    return subject, text, html

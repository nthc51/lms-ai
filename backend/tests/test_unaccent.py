from sqlalchemy import text


async def test_unaccent_removes_vietnamese_marks(db):
    assert await db.scalar(text("SELECT immutable_unaccent('Tìm kiếm nhị phân')")) == "Tim kiem nhi phan"


async def test_unaccent_handles_d_stroke(db):
    assert await db.scalar(text("SELECT immutable_unaccent('Đồ thị đường đi')")) == "Do thi duong di"


async def test_unaccent_function_is_immutable(db):
    vol = await db.scalar(text("SELECT provolatile::text FROM pg_proc WHERE proname = 'immutable_unaccent'"))
    assert vol == "i"

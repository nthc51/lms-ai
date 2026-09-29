# Trần cho query param `page`: số lớn hơn sẽ tràn int64 khi tính OFFSET → 500. Chặn ở 422.
MAX_PAGE = 10_000

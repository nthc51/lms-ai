"""Retry dùng chung cho các lời gọi Gemini: chỉ thử lại khi 429, 5xx hoặc timeout."""

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger("app.ai")

Sleep = Callable[[float], Awaitable[None]]

MAX_RETRIES = 3
BASE_DELAY_S = 1.0
# Trần cho Retry-After: server trả giá trị quá lớn cũng không giữ worker chờ lâu hơn mức này
MAX_RETRY_AFTER_S = 60.0


def _status_code(exc: BaseException) -> int | None:
    from google.genai import errors

    return exc.code if isinstance(exc, errors.APIError) else None


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return True
    code = _status_code(exc)
    return code is not None and (code == 429 or 500 <= code <= 599)


def _retry_info_delay(exc: BaseException) -> float | None:
    """retryDelay trong thân lỗi Gemini (google.rpc.RetryInfo, vd. "10.28s"). Gemini báo thời gian chờ ở đây
    khi hết quota theo phút, thường không kèm header Retry-After."""
    body = getattr(exc, "details", None)
    error = body.get("error") if isinstance(body, dict) else None
    items = error.get("details") if isinstance(error, dict) else None
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("RetryInfo"):
            value = str(item.get("retryDelay", "")).removesuffix("s")
            try:
                return float(value)
            except ValueError:
                return None
    return None


def retry_after_s(exc: BaseException) -> float | None:
    """Giây chờ server yêu cầu: header Retry-After của response lỗi (APIError.response là httpx.Response),
    không có thì retryDelay trong thân lỗi (RetryInfo). Tối đa MAX_RETRY_AFTER_S. Không có, không phải số,
    âm hoặc không hữu hạn (inf/nan) → None (dùng backoff)."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    value = headers.get("retry-after") if headers is not None else None
    try:
        delay = float(value) if value is not None else _retry_info_delay(exc)
    except ValueError:
        return None
    if delay is None or not math.isfinite(delay) or delay < 0:
        return None
    return min(delay, MAX_RETRY_AFTER_S)


async def call_with_retry[T](
    op: str,
    fn: Callable[[], Awaitable[T]],
    *,
    sleep: Sleep = asyncio.sleep,
    max_retries: int = MAX_RETRIES,
    base_delay_s: float = BASE_DELAY_S,
) -> T:
    start = time.perf_counter()
    attempt = 0
    while True:
        try:
            result = await fn()
        except Exception as exc:
            if not is_retryable(exc) or attempt >= max_retries:
                logger.warning(
                    "ai_call op=%s status=error attempts=%d latency_ms=%d error=%r",
                    op,
                    attempt + 1,
                    (time.perf_counter() - start) * 1000,
                    exc,
                )
                raise
            delay = retry_after_s(exc)
            if delay is None:
                delay = base_delay_s * 2**attempt
            attempt += 1
            await sleep(delay)
            continue
        logger.info(
            "ai_call op=%s status=ok attempts=%d latency_ms=%d",
            op,
            attempt + 1,
            (time.perf_counter() - start) * 1000,
        )
        return result

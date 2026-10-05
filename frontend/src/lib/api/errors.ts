export type ApiErrorBody = {
  error: { code: string; message: string; details?: Record<string, unknown>; request_id?: string | null };
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId: string | null = null,
    public details: Record<string, unknown> = {},
    public retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Lỗi 422 của một trường cụ thể, vd. fieldError("email"). */
  fieldError(field: string): string | undefined {
    const errors = (this.details.errors ?? []) as { loc: (string | number)[]; msg: string }[];
    return errors.find((e) => e.loc[e.loc.length - 1] === field)?.msg;
  }
}

const NETWORK_MESSAGE = "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.";

export async function toApiError(res: Response): Promise<ApiError> {
  const retryAfterHeader = res.headers.get("Retry-After");
  const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : null;
  const requestId = res.headers.get("x-request-id");
  try {
    const body = (await res.clone().json()) as ApiErrorBody;
    if (body?.error?.code) {
      const e = body.error;
      return new ApiError(res.status, e.code, e.message, e.request_id ?? requestId, e.details ?? {}, retryAfter);
    }
  } catch {
    // thân không phải JSON (vd. 502 từ proxy)
  }
  const message = res.status >= 500 ? "Máy chủ đang gặp sự cố. Thử lại sau ít phút." : "Yêu cầu không hợp lệ";
  return new ApiError(res.status, "HTTP_ERROR", message, requestId, {}, retryAfter);
}

export function networkError(): ApiError {
  return new ApiError(0, "NETWORK_ERROR", NETWORK_MESSAGE);
}

/** Câu thông báo cho người dùng từ một lỗi bất kỳ. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429 && err.retryAfter) return `Bạn thao tác hơi nhanh, thử lại sau ${err.retryAfter} giây.`;
    return err.message;
  }
  return "Đã có lỗi xảy ra. Thử lại nhé.";
}

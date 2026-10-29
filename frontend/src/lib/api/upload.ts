import { api, unwrap } from "./client";

export type UploadKind = "pdf" | "video" | "submission";
export type UploadProgress = (pct: number) => void;

/** PUT file lên presigned URL của MinIO bằng XHR (fetch chưa báo được tiến trình upload). */
export function putWithProgress(url: string, file: File, onProgress: UploadProgress, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload lỗi (${xhr.status})`)));
    xhr.onerror = () => reject(new Error("Mất kết nối khi tải file lên"));
    xhr.onabort = () => reject(new DOMException("Đã hủy", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(file);
  });
}

/** presign → PUT (có tiến trình) → complete. Trả về asset_id đã được server xác minh. */
export async function uploadAsset(kind: UploadKind, file: File, onProgress: UploadProgress, signal?: AbortSignal) {
  const { asset_id, put_url } = await unwrap(
    api.POST("/api/v1/uploads/presign", { body: { kind, mime: file.type, size: file.size, filename: file.name } }),
  );
  await putWithProgress(put_url, file, onProgress, signal);
  await unwrap(api.POST("/api/v1/uploads/{asset_id}/complete", { params: { path: { asset_id } } }));
  return asset_id;
}

export const UPLOAD_RULES: Record<UploadKind, { mime: string; maxBytes: number; label: string }> = {
  pdf: { mime: "application/pdf", maxBytes: 50 * 1024 * 1024, label: "PDF, tối đa 50 MB" },
  video: { mime: "video/mp4", maxBytes: 500 * 1024 * 1024, label: "MP4, tối đa 500 MB" },
  // bài nộp của học viên (B5): mime là danh sách cách nhau bằng dấu phẩy, dùng luôn cho thuộc tính accept
  submission: { mime: "application/pdf,text/plain", maxBytes: 20 * 1024 * 1024, label: "PDF hoặc .txt, tối đa 20 MB" },
};

/** Kiểm tra trước khi gọi API, để báo lỗi ngay thay vì đợi server từ chối. */
export function validateFile(kind: UploadKind, file: File): string | null {
  const rule = UPLOAD_RULES[kind];
  if (!rule.mime.split(",").includes(file.type)) return `Chỉ nhận file ${rule.label.split(",")[0]}`;
  if (file.size > rule.maxBytes) return `File quá lớn (${rule.label})`;
  return null;
}

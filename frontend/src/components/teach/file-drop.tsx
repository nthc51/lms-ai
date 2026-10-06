"use client";

import { Upload } from "lucide-react";
import * as React from "react";
import { Progress } from "@/components/ui/misc";
import { UPLOAD_RULES, type UploadKind, uploadAsset, validateFile } from "@/lib/api/upload";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/**
 * Vùng kéo thả + nút chọn file, có thanh tiến trình %. Gọi onUploaded(assetId, file) khi
 * presign → PUT → complete xong (design-system §5.3: "Tải PDF lên").
 */
export function FileDrop({
  kind,
  label,
  onUploaded,
  disabled,
}: {
  kind: UploadKind;
  label: string;
  onUploaded: (assetId: string, file: File) => Promise<unknown>;
  disabled?: boolean;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);
  const [progress, setProgress] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const id = React.useId();

  async function handle(file: File | undefined) {
    if (!file) return;
    setError(null);
    const invalid = validateFile(kind, file);
    if (invalid) return setError(invalid);
    setProgress(0);
    try {
      const assetId = await uploadAsset(kind, file, setProgress);
      await onUploaded(assetId, file);
    } catch (err) {
      setError(err instanceof Error && !("status" in err) ? err.message : errorMessage(err));
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const busy = progress !== null;
  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy && !disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!busy && !disabled) void handle(e.dataTransfer.files[0]);
        }}
        className={cn(
          "flex flex-col items-center gap-2 rounded-lg border border-dashed p-5 text-center text-sm",
          over && "border-primary bg-primary/5",
        )}
      >
        {busy ? (
          <div className="w-full" aria-live="polite">
            <p className="mb-2">Đang tải lên… {progress}%</p>
            <Progress value={progress ?? 0} label="Tiến trình tải lên" />
          </div>
        ) : (
          <>
            <Upload className="size-6 text-muted-foreground" aria-hidden />
            <p className="text-muted-foreground">Kéo thả file vào đây hoặc</p>
            <label
              htmlFor={id}
              className={cn(
                "inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border px-4 font-medium hover:bg-muted md:h-8",
                disabled && "pointer-events-none opacity-50",
              )}
            >
              {label}
            </label>
            <p className="text-xs text-muted-foreground">{UPLOAD_RULES[kind].label}</p>
          </>
        )}
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept={UPLOAD_RULES[kind].mime}
          className="sr-only"
          disabled={busy || disabled}
          onChange={(e) => void handle(e.target.files?.[0])}
        />
      </div>
      {error ? (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Đọc thời lượng video ngay trên trình duyệt để lưu duration_sec. */
export function readVideoDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(v.duration) ? Math.round(v.duration) : null);
    };
    v.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    v.src = url;
  });
}

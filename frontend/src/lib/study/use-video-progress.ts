"use client";

import * as React from "react";
import type { LessonDetail } from "@/lib/queries";
import { useSaveProgress } from "@/lib/queries";

const SAVE_EVERY_SEC = 15;

/**
 * Lưu vị trí video lên server (PUT /lessons/{id}/progress) mỗi 15 giây xem,
 * khi tạm dừng và khi rời trang; mở lại thì tua tới chỗ cũ.
 * Chỉ học viên mới lưu được (backend trả 403 cho giảng viên) → `track=false`.
 */
export function useVideoProgress(lesson: LessonDetail, track: boolean) {
  const save = useSaveProgress(lesson.id);
  const lastSaved = React.useRef(lesson.progress?.video_position_sec ?? 0);
  const done = lesson.progress?.status === "done";

  const persist = React.useCallback(
    (sec: number) => {
      if (!track) return;
      const pos = Math.floor(sec);
      if (Math.abs(pos - lastSaved.current) < 2) return;
      lastSaved.current = pos;
      save.mutate({ status: done ? "done" : "in_progress", video_position_sec: pos });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [track, done, lesson.id],
  );

  const bind = React.useCallback(
    (video: HTMLVideoElement | null) => {
      if (!video) return;
      const resumeAt = lesson.progress?.video_position_sec ?? 0;
      const onMeta = () => {
        if (resumeAt > 5 && resumeAt < video.duration - 5) video.currentTime = resumeAt;
      };
      const onTime = () => {
        if (Math.abs(video.currentTime - lastSaved.current) >= SAVE_EVERY_SEC) persist(video.currentTime);
      };
      const onPause = () => persist(video.currentTime);
      video.addEventListener("loadedmetadata", onMeta);
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("pause", onPause);
      const onHide = () => document.visibilityState === "hidden" && persist(video.currentTime);
      document.addEventListener("visibilitychange", onHide);
      return () => {
        video.removeEventListener("loadedmetadata", onMeta);
        video.removeEventListener("timeupdate", onTime);
        video.removeEventListener("pause", onPause);
        document.removeEventListener("visibilitychange", onHide);
      };
    },
    [lesson.progress?.video_position_sec, persist],
  );

  return { bind, currentSaved: () => lastSaved.current };
}

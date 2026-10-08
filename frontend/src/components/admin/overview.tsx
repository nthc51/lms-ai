"use client";

import { AlertTriangle, BookOpen, Lock, ClipboardCheck, GraduationCap, type LucideIcon, MessageCircleQuestion, ThumbsDown, UserCheck, Users } from "lucide-react";
import Link from "next/link";
import { type AdminStats } from "@/lib/admin-queries";
import { cn } from "@/lib/utils";

function Tile({ icon: Icon, label, value, sub, href, highlight }: { icon: LucideIcon; label: string; value: number; sub?: string; href?: string; highlight?: boolean }) {
  const body = (
    <>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className={cn("size-4", highlight && "text-accent")} aria-hidden />
        {label}
      </div>
      <p className="mt-2 text-3xl font-semibold tabular-nums">{value.toLocaleString("vi-VN")}</p>
      {sub ? <p className="mt-1 text-xs text-muted-foreground">{sub}</p> : null}
    </>
  );
  const cls = cn("block rounded-lg border bg-surface p-4", highlight && "border-accent/60", href && "transition-colors hover:bg-muted");
  return href ? (
    <Link href={href} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/** Ô số liệu tổng quan. Ô "Chờ duyệt" nổi bật khi có người đang chờ và dẫn thẳng tới danh sách. */
export function StatTiles({ s }: { s: AdminStats }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile icon={UserCheck} label="Giảng viên chờ duyệt" value={s.pending_teachers} href="/admin/users?tab=pending" highlight={s.pending_teachers > 0} sub={s.pending_teachers > 0 ? "Bấm để xử lý" : "Không có ai đang chờ"} />
      <Tile icon={Users} label="Học viên" value={s.students} sub={`${s.enrollments.toLocaleString("vi-VN")} lượt đăng ký khóa`} href="/admin/users?tab=student" />
      <Tile icon={GraduationCap} label="Giảng viên" value={s.teachers} href="/admin/users?tab=teacher" />
      <Tile icon={Lock} label="Tài khoản bị khóa" value={s.locked_users} href="/admin/users?tab=locked" />
      <Tile icon={BookOpen} label="Khóa đã xuất bản" value={s.courses_published} sub={`${s.courses_draft} nháp · ${s.courses_hidden} đã ẩn`} href="/admin/courses" />
      <Tile icon={MessageCircleQuestion} label="Câu hỏi AI Tutor (7 ngày)" value={s.tutor_questions_7d} />
      <Tile icon={ClipboardCheck} label="Bài quiz đã nộp (7 ngày)" value={s.quiz_submissions_7d} />
      <Tile icon={ThumbsDown} label="Trả lời AI bị chê (7 ngày)" value={s.tutor_downvotes_7d} href="/admin/feedback" sub="Xem câu hỏi và câu trả lời" />
      <Tile icon={AlertTriangle} label="Tác vụ AI lỗi (7 ngày)" value={s.failed_jobs_7d} highlight={s.failed_jobs_7d > 0} sub="Xử lý tài liệu, sinh câu hỏi" />
    </div>
  );
}

const dayFmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "UTC" });

/** Cột đăng ký mới 14 ngày. Một chuỗi số liệu nên không cần chú thích; có bảng ẩn cho trình đọc màn hình. */
export function SignupChart({ days }: { days: AdminStats["signups_14d"] }) {
  if (days.length === 0) return null;
  const max = Math.max(1, ...days.map((d) => d.count));
  const total = days.reduce((a, d) => a + d.count, 0);
  const label = (d: { day: string }) => dayFmt.format(new Date(`${d.day}T00:00:00Z`));
  return (
    <figure className="rounded-lg border bg-surface p-4">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="font-semibold">Người dùng mới 14 ngày qua</span>
        <span className="text-sm text-muted-foreground tabular-nums">Tổng {total}</span>
      </figcaption>
      <div className="mt-4 flex h-32 items-end gap-1" aria-hidden>
        {days.map((d) => (
          <div key={d.day} className="group relative flex h-full flex-1 flex-col justify-end" title={`${label(d)}: ${d.count} người`}>
            <div className="rounded-t-[4px] bg-primary transition-opacity group-hover:opacity-80" style={{ height: `${(d.count / max) * 100}%`, minHeight: d.count ? 4 : 0 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted-foreground" aria-hidden>
        <span>{label(days[0])}</span>
        <span>{label(days[days.length - 1])}</span>
      </div>
      <table className="sr-only">
        <caption>Số người dùng mới theo ngày</caption>
        <tbody>
          {days.map((d) => (
            <tr key={d.day}>
              <th scope="row">{label(d)}</th>
              <td>{d.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

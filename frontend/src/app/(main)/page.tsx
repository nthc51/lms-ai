"use client";

import { Clock, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/app/states";
import { MyCourseList, ResumeCard } from "@/components/course/my-course-list";
import { Landing } from "@/components/landing/landing";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { api, unwrap } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { type User, useAuth } from "@/lib/auth/auth-context";

/** Tên gọi: chữ cuối của họ tên Việt ("Nguyễn Văn An" → "An"). */
const givenName = (fullName: string) => fullName.trim().split(/\s+/).slice(-1)[0] ?? fullName;

/** Giảng viên chưa được duyệt: nói rõ đang chờ hay đã bị từ chối (kèm lý do quản trị viên ghi). */
function TeacherReviewNotice({ user }: { user: User }) {
  const { reloadUser } = useAuth();
  const [sending, setSending] = React.useState(false);
  if (user.role !== "teacher" || user.teacher_status === "approved") return null;

  async function askAgain() {
    setSending(true);
    try {
      await unwrap(api.POST("/api/v1/me/teacher-request"));
      await reloadUser();
      toast.success("Đã gửi lại yêu cầu duyệt");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  const rejected = user.teacher_status === "rejected";
  const Icon = rejected ? XCircle : Clock;
  return (
    <section aria-label="Trạng thái tài khoản giảng viên" className="mb-6 flex gap-3 rounded-lg border p-4">
      <Icon className={rejected ? "mt-0.5 size-5 shrink-0 text-destructive" : "mt-0.5 size-5 shrink-0 text-accent"} aria-hidden />
      <div>
        <p className="font-medium">{rejected ? "Yêu cầu giảng dạy chưa được chấp nhận" : "Tài khoản giảng viên đang chờ duyệt"}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {rejected
            ? `Lý do: ${user.review_note ?? "không ghi"}. Bạn có thể gửi lại yêu cầu để được xem xét lại.`
            : "Quản trị viên sẽ duyệt sớm và báo kết quả qua email. Trong lúc chờ, bạn vẫn xem được các khóa học đã xuất bản."}
        </p>
        {rejected ? (
          <Button variant="outline" size="sm" className="mt-3" onClick={askAgain} loading={sending} loadingText="Đang gửi…">
            Gửi lại yêu cầu duyệt
          </Button>
        ) : null}
      </div>
    </section>
  );
}

export default function HomePage() {
  const { user, status } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";
  // Quản trị viên không học cũng không dạy: trang chủ của họ là khu quản trị.
  React.useEffect(() => {
    if (isAdmin) router.replace("/admin");
  }, [isAdmin, router]);
  if (status === "loading" || isAdmin) return <Skeleton className="h-40 w-full" />;

  // Khách: trang giới thiệu riêng, không nằm trong khung app (AppShell bỏ khung ở "/" khi chưa đăng nhập).
  if (!user) return <Landing />;

  // Chỉ giảng viên đã duyệt mới vào được /teach.
  const canTeach = user.role === "teacher" && user.teacher_status === "approved";

  return (
    <>
      <PageHeader title={`Chào ${givenName(user.full_name)}`}>
        {user.role === "student" ? "Tiếp tục từ chỗ bạn đã dừng." : canTeach ? "Quản lý các khóa bạn đang dạy." : "Chào mừng bạn đến với LMS-AI."}
      </PageHeader>
      <TeacherReviewNotice user={user} />
      {user.role === "student" ? (
        <>
          <ResumeCard />
          <MyCourseList limit={3} moreHref="/my" />
        </>
      ) : (
        <Button asChild>
          <Link href={canTeach ? "/teach" : "/explore"}>{canTeach ? "Tới khóa đang dạy" : "Khám phá khóa học"}</Link>
        </Button>
      )}
    </>
  );
}

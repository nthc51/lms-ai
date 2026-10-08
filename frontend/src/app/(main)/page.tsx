"use client";

import { ArrowRight, Clock, Compass, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/app/states";
import { MyCourseList } from "@/components/course/my-course-list";
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
    <div role="status" className="mb-6 flex gap-3 rounded-lg border p-4">
      <Icon className={rejected ? "mt-0.5 size-5 shrink-0 text-destructive" : "mt-0.5 size-5 shrink-0 text-accent"} aria-hidden />
      <div>
        <p className="font-medium">{rejected ? "Yêu cầu giảng dạy chưa được chấp nhận" : "Tài khoản giảng viên đang chờ duyệt"}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {rejected
            ? `Lý do: ${user.review_note ?? "không ghi"}. Bổ sung thông tin rồi gửi lại yêu cầu để được xem xét lại.`
            : "Quản trị viên sẽ duyệt sớm và báo kết quả qua email. Trong lúc chờ, bạn vẫn xem được các khóa học đã xuất bản."}
        </p>
        {rejected ? (
          <Button variant="outline" size="sm" className="mt-3" onClick={askAgain} loading={sending} loadingText="Đang gửi…">
            Gửi lại yêu cầu duyệt
          </Button>
        ) : null}
      </div>
    </div>
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

  if (!user)
    return (
      <section className="mx-auto max-w-2xl py-10 text-center md:py-20">
        <h1 className="text-3xl font-semibold md:text-4xl">Học theo nhịp của bạn, có AI giải đáp ngay trong bài</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          AI Tutor trả lời dựa trên đúng tài liệu của khóa học và luôn ghi nguồn, để bạn kiểm chứng được.
        </p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/explore">
              <Compass /> Khám phá khóa học
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/register">Tạo tài khoản</Link>
          </Button>
        </div>
      </section>
    );

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
          <MyCourseList limit={3} />
          <Button asChild variant="link" className="mt-4">
            <Link href="/my">
              Xem tất cả khóa của tôi <ArrowRight />
            </Link>
          </Button>
        </>
      ) : (
        <Button asChild>
          <Link href={canTeach ? "/teach" : "/explore"}>{canTeach ? "Tới khóa đang dạy" : "Khám phá khóa học"}</Link>
        </Button>
      )}
    </>
  );
}

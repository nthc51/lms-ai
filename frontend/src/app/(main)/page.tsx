"use client";

import { ArrowRight, Compass } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/app/states";
import { MyCourseList } from "@/components/course/my-course-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth/auth-context";

export default function HomePage() {
  const { user, status } = useAuth();
  if (status === "loading") return <Skeleton className="h-40 w-full" />;

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

  // Chỉ giảng viên đã duyệt mới vào được /teach (admin gọi API soạn khóa sẽ nhận 403).
  const canTeach = user.role === "teacher" && user.teacher_status === "approved";

  return (
    <>
      <PageHeader title={`Chào ${user.full_name.split(" ").slice(-1)[0]}`}>
        {user.role === "student" ? "Tiếp tục từ chỗ bạn đã dừng." : "Quản lý các khóa bạn đang dạy."}
      </PageHeader>
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

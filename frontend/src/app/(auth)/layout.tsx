import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <Link href="/" className="mb-8 flex items-center gap-2 text-lg font-semibold">
        <span className="grid size-9 place-items-center rounded-md bg-primary text-primary-foreground">L</span>
        LMS-AI
      </Link>
      <main className="w-full max-w-sm rounded-lg border bg-surface p-6">{children}</main>
    </div>
  );
}

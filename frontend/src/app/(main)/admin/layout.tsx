import { RequireAuth } from "@/lib/auth/require-auth";

export const metadata = { title: "Quản trị" };

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <RequireAuth admin>{children}</RequireAuth>;
}

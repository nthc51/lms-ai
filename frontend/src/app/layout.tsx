import "@fontsource/be-vietnam-pro/400.css";
import "@fontsource/be-vietnam-pro/500.css";
import "@fontsource/be-vietnam-pro/600.css";
import "@fontsource-variable/noto-sans";
import "@fontsource-variable/jetbrains-mono";
import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "LMS-AI", template: "%s · LMS-AI" },
  description: "Nền tảng học trực tuyến có AI Tutor trả lời theo tài liệu khóa học",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f5f0" },
    { media: "(prefers-color-scheme: dark)", color: "#171a1e" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body className="min-h-dvh antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

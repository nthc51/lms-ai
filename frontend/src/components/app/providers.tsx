"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import * as React from "react";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/misc";
import { ApiError } from "@/lib/api/errors";
import { AuthProvider } from "@/lib/auth/auth-context";

export const THEMES = ["light", "dark", "sepia"] as const;

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // không thử lại lỗi 4xx (sai quyền, không tồn tại); chỉ thử lại lỗi mạng/5xx một lần
        retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 1,
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" themes={[...THEMES]} defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        </AuthProvider>
        <ResponsiveToaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}

/** Toast: góc dưới phải trên desktop, trên cùng trên điện thoại, tự tắt 4 giây (design-system §6). */
function ResponsiveToaster() {
  const [mobile, setMobile] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return (
    <Toaster
      position={mobile ? "top-center" : "bottom-right"}
      duration={4000}
      toastOptions={{ className: "!bg-surface !text-foreground !border-border font-sans" }}
    />
  );
}

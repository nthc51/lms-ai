import type { NextConfig } from "next";

// Trình duyệt chỉ gọi cùng origin (/api/v1/...), Next chuyển tiếp sang FastAPI.
// Nhờ vậy cookie refresh (path=/api/v1/auth, SameSite=Lax) hoạt động mà không cần CORS.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: { proxyTimeout: 120000 },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` }];
  },
};

export default nextConfig;

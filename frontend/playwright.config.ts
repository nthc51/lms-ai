import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 3100);

// E2E chạy với API giả (page.route trong e2e/mock-api.ts) nên không cần backend/Gemini.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    locale: "vi-VN",
    // Máy đã có sẵn Chromium khác phiên bản thì trỏ tới đó: PW_CHROMIUM=/đường/dẫn/chrome
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  projects: [
    { name: "mobile-375", use: { ...devices["Pixel 7"], viewport: { width: 375, height: 812 } } },
    { name: "desktop-1280", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    command: `npm run build && npx next start -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    // API_ORIGIN trỏ vào cổng không có gì: mọi request /api/v1 phải được mock, lọt ra là lỗi
    env: { API_ORIGIN: "http://127.0.0.1:9" },
  },
});

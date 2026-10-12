import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://api:8000";

export const options = {
  scenarios: {
    browse: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 50 },
        { duration: "2m", target: 50 },
        { duration: "20s", target: 0 },
      ],
    },
  },
  thresholds: { http_req_failed: ["rate<0.01"], "http_req_duration{name:catalog}": ["p(95)<500"] },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "max"],
};

export function setup() {
  const r = http.get(`${BASE}/api/v1/courses?page=1&size=20`);
  const items = r.json("items") || [];
  if (items.length === 0) throw new Error("Chưa có khóa học publish, hãy chạy scripts.perf_seed trước");
  return { slugs: items.map((c) => c.slug) };
}

export default function (data) {
  const page = 1 + Math.floor(Math.random() * 2);
  const r1 = http.get(`${BASE}/api/v1/courses?page=${page}&size=10`, { tags: { name: "catalog" } });
  check(r1, { "catalog 200": (r) => r.status === 200 });

  const slug = data.slugs[Math.floor(Math.random() * data.slugs.length)];
  const r2 = http.get(`${BASE}/api/v1/courses/${slug}`, { tags: { name: "detail" } });
  check(r2, { "detail 200": (r) => r.status === 200 });
  sleep(1);
}

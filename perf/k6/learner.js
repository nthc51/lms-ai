import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://api:8000";
const seed = JSON.parse(open("/perf/seed.json"));

export const options = {
  scenarios: {
    learners: {
      executor: "constant-vus",
      vus: 30,
      duration: "2m",
    },
  },
  thresholds: { http_req_failed: ["rate<0.01"], "http_req_duration{name:lesson}": ["p(95)<500"] },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "max"],
};

// Đăng nhập 10 tài khoản một lần (dưới giới hạn LOGIN_RATE_LIMIT_PER_MIN = 20 lần/phút/IP), các VU dùng chung token
export function setup() {
  const tokens = seed.students.map((email) => {
    const r = http.post(`${BASE}/api/v1/auth/login`, JSON.stringify({ email, password: seed.password }),
      { headers: { "Content-Type": "application/json" } });
    if (r.status !== 200) throw new Error(`Đăng nhập ${email} lỗi ${r.status}`);
    return r.json("access_token");
  });
  return { tokens };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  const params = (name) => ({ headers: { Authorization: `Bearer ${token}` }, tags: { name } });

  const r1 = http.get(`${BASE}/api/v1/me/courses`, params("my_courses"));
  check(r1, { "my courses 200": (r) => r.status === 200 });

  const lessonId = seed.lesson_ids[Math.floor(Math.random() * seed.lesson_ids.length)];
  const r2 = http.get(`${BASE}/api/v1/lessons/${lessonId}`, params("lesson"));
  check(r2, { "lesson 200": (r) => r.status === 200 });

  const r3 = http.put(`${BASE}/api/v1/lessons/${lessonId}/progress`,
    JSON.stringify({ status: "in_progress", video_position_sec: 30 }),
    { headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, tags: { name: "progress" } });
  check(r3, { "progress 200": (r) => r.status === 200 });
  sleep(1);
}

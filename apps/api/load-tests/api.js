import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    http_req_failed: ["rate<0.05"],
  },
};

export default function () {
  const base = __ENV.API_URL || "http://localhost:8000";

  const health = http.get(`${base}/health/live`);
  check(health, { "health/live returns 200": (r) => r.status === 200 });

  const ready = http.get(`${base}/health/ready`);
  check(ready, { "health/ready returns 200/503": (r) => r.status === 200 || r.status === 503 });

  sleep(1);
}

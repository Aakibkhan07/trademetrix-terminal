import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const failRate = new Rate('failed_requests');
const authDuration = new Trend('auth_duration');

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '1m', target: 50 },
    { duration: '30s', target: 100 },
    { duration: '1m', target: 100 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    failed_requests: ['rate<0.05'],
    http_req_duration: ['p(95)<500'],
    auth_duration: ['p(95)<1000'],
  },
};

const USER_CREDENTIALS = {
  email: `loadtest_${__VU}@example.com`,
  password: 'LoadTest123!',
};

export default function () {
  group('Auth Flow', () => {
    const signupRes = http.post(`${BASE_URL}/api/v1/auth/signup`, JSON.stringify(USER_CREDENTIALS), {
      headers: { 'Content-Type': 'application/json' },
    });
    authDuration.add(signupRes.timings.duration);
    check(signupRes, { 'signup ok': (r) => r.status === 201 || r.status === 409 });

    const signinRes = http.post(`${BASE_URL}/api/v1/auth/signin`, JSON.stringify(USER_CREDENTIALS), {
      headers: { 'Content-Type': 'application/json' },
    });
    check(signinRes, { 'signin ok': (r) => r.status === 200 });
    failRate.add(signinRes.status !== 200);

    const token = signinRes.json('access_token');
    const headers = { Authorization: `Bearer ${token}` };

    group('API Endpoints', () => {
      const endpoints = [
        ['GET', '/health'],
        ['GET', '/metrics'],
        ['GET', '/api/v1/auth/me', headers],
        ['GET', '/api/v1/strategies/list-builtin'],
        ['GET', '/api/v1/risk/kill-switch', headers],
        ['GET', '/api/v1/risk/live/status', headers],
        ['GET', '/api/v1/brokers/list'],
      ];

      endpoints.forEach(([method, path, h]) => {
        const opts = h ? { headers: h } : {};
        const res = http.request(method, `${BASE_URL}${path}`, null, opts);
        check(res, { [`${path} ok`]: (r) => r.status < 500 });
        failRate.add(res.status >= 500);
      });
    });

    sleep(1);
  });
}

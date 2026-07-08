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

// Shared credentials seeded once in setup()
const EMAIL = `loadtest_runner@example.com`;
const PASSWORD = 'LoadTest123!';
let sharedToken = null;

export function setup() {
  // Create the test user once (ignore 409 if already exists)
  const signupRes = http.post(`${BASE_URL}/api/v1/auth/signup`, JSON.stringify({
    email: EMAIL,
    password: PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' } });
  console.log(`setup signup: ${signupRes.status}`);

  // Sign in to get a token
  const signinRes = http.post(`${BASE_URL}/api/v1/auth/signin`, JSON.stringify({
    email: EMAIL,
    password: PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' } });
  console.log(`setup signin: ${signinRes.status}`);
  if (signinRes.status === 200) {
    return { token: signinRes.json('access_token') };
  }
  return { token: '' };
}

export default function (data) {
  const token = data.token;
  if (!token) {
    failRate.add(1);
    return;
  }
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
}

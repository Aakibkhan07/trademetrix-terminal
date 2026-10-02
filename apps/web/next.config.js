/** @type {import('next').NextConfig} */

// Development needs two things this policy did not allow, and both blocked the app from
// running locally at all:
//
//   1. `'unsafe-eval'` in `script-src`. The dev runtime evaluates compiled module code —
//      React Refresh does this — so without it the browser refuses, hydration throws, and the
//      client bundle never takes over. The visible symptom is a page frozen on its skeleton
//      loaders with **zero** network requests: the server-rendered HTML arrives, and nothing
//      after it ever runs. It looks like a data-loading bug and is not one.
//   2. The API's own origin in `connect-src`. It was hardcoded to
//      `https://api.ai.trademetrix.tech`, so pointing `NEXT_PUBLIC_API_URL` anywhere else was
//      silently overridden by this header — the browser blocked every call with a CSP error
//      while the config file looked correct.
//
// The API origin is now derived from `NEXT_PUBLIC_API_URL` instead of being written down
// twice. With the production value of that variable the emitted header is unchanged, which is
// the point: production keeps exactly the policy it has today, with no `unsafe-eval`.
//
// A production build does not evaluate compiled module code, so it does not need
// `'unsafe-eval'` and must not be given it.

const isDev = process.env.NODE_ENV !== 'production';

/** Scheme + host + port of the API, without its path, as CSP `connect-src` wants it. */
function apiOrigins(rawUrl) {
  const base = rawUrl || 'https://api.ai.trademetrix.tech/api/v1';
  try {
    const u = new URL(base);
    const http = `${u.protocol}//${u.host}`;
    const ws = `${u.protocol === 'https:' ? 'wss:' : 'ws:'}//${u.host}`;
    return `${http} ${ws}`;
  } catch {
    // A malformed URL must not produce a policy with an `undefined` in it, which would be
    // silently ignored by the browser and leave connect-src effectively empty.
    return 'https://api.ai.trademetrix.tech wss://api.ai.trademetrix.tech';
  }
}

const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""} https://www.clarity.ms https://*.clarity.ms https://checkout.razorpay.com`,
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://checkout.razorpay.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: https://www.clarity.ms https://*.clarity.ms https://api.razorpay.com",
  `connect-src 'self' ${apiOrigins(process.env.NEXT_PUBLIC_API_URL)} https://www.clarity.ms https://*.clarity.ms wss://*.clarity.ms https://api.razorpay.com`,
  "frame-src https://checkout.razorpay.com",
  "frame-ancestors 'none'",
  "base-uri 'self'",
].join('; ');

const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains; preload" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Content-Security-Policy", value: csp },
];

const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'ai.trademetrix.tech' },
      { protocol: 'https', hostname: 'api.ai.trademetrix.tech' },
    ],
  },
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
}

module.exports = nextConfig

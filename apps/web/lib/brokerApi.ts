// Portal <-> backend broker-connect client.
// Mirrors the platform's CSRF handshake used in lib/api.ts (cookie
// `csrf_token` + header `X-CSRF-Token`, fetched from /api/v1/auth/csrf) so
// POSTs pass the global CSRFProtectMiddleware. The httpOnly session cookie is
// sent automatically via credentials: "include".

// Origin of the API (no /api/v1 suffix) — broker routes mount at /api/broker/*.
const ORIGIN = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const CSRF_URL = `${ORIGIN}/api/v1/auth/csrf`;

export type BrokerKey =
  | "kotak"
  | "zerodha"
  | "upstox"
  | "angelone"
  | "fyers"
  | "dhan"
  | "lemonn"
  | "kotakneo";

export interface BrokerInfo {
  key: BrokerKey;
  configured: boolean;
  coming_soon: boolean;
  credential_login?: boolean;
  credential_fields?: CredentialField[];
  instructions?: string;
}

export interface CredentialField {
  key: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  type?: string;
}

export interface BrokerConnection {
  broker: BrokerKey;
  status: string;
  is_live: boolean;
  broker_user_id?: string | null;
  token_expires_at?: string;
}

// --- CSRF (kept in sync with lib/api.ts) -----------------------------------
let _csrfFetching = false;
let _csrfPromise: Promise<void> | null = null;

function getCSRFToken(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function ensureCSRF(): Promise<void> {
  if (typeof document === "undefined") return;
  if (document.cookie.includes("csrf_token=") || _csrfFetching) return;
  if (_csrfPromise) return _csrfPromise;
  _csrfFetching = true;
  _csrfPromise = (async () => {
    try {
      await fetch(CSRF_URL, { credentials: "include" });
    } catch {
      /* best-effort */
    } finally {
      _csrfFetching = false;
      _csrfPromise = null;
    }
  })();
  return _csrfPromise;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureCSRF();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const csrf = getCSRFToken();
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(`${ORIGIN}${path}`, {
    credentials: "include",
    ...init,
    headers,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as any).detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function getAvailableBrokers() {
  return req<{ brokers: BrokerInfo[] }>("/api/broker/available");
}

export function getConnections() {
  return req<{ connections: BrokerConnection[] }>("/api/broker/status");
}

export async function startConnect(broker: BrokerKey) {
  const { authorization_url } = await req<{ authorization_url: string }>(
    "/api/broker/connect",
    { method: "POST", body: JSON.stringify({ broker }) }
  );
  // Full-page redirect to the broker's own login (no popup, no iframe —
  // brokers block embedding). User authenticates on the broker's domain.
  window.location.assign(authorization_url);
}

export function disconnectBroker(broker: BrokerKey) {
  return req<{ ok: boolean }>("/api/broker/disconnect", {
    method: "POST",
    body: JSON.stringify({ broker }),
  });
}

export function connectWithCredentials(
  broker: BrokerKey,
  consumer_key: string,
  credentials: Record<string, string>
) {
  return req<{ ok: boolean; broker: string; broker_user_id: string | null }>(
    "/api/broker/connect-credentials",
    {
      method: "POST",
      body: JSON.stringify({ broker, consumer_key, credentials }),
    }
  );
}

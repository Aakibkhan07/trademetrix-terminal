const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export interface AdminUser {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  subscription_tier: string
  active_assignments: number
  max_active_strategies: number
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface ApiOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

function getCSRFToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, signal } = options

  const finalHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...headers,
  }

  const csrf = getCSRFToken()
  if (csrf && method !== 'GET') {
    finalHeaders['X-CSRF-Token'] = csrf
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: finalHeaders,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })

  if (res.status === 204) return undefined as T

  const data = await res.json()

  if (!res.ok) {
    throw new ApiError(res.status, data.detail || `Request failed: ${res.status}`)
  }

  return data as T
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) => request<T>(path, { method: 'POST', body, signal }),
  put: <T>(path: string, body?: unknown, signal?: AbortSignal) => request<T>(path, { method: 'PUT', body, signal }),
  patch: <T>(path: string, body?: unknown, signal?: AbortSignal) => request<T>(path, { method: 'PATCH', body, signal }),
  delete: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: 'DELETE', signal }),

  auth: {
    signup: (data: { email: string; password: string; full_name?: string }) =>
      request<{ access_token: string; user?: { email: string; full_name?: string } }>('/auth/signup', { method: 'POST', body: data }),
    signin: (data: { email: string; password: string }) =>
      request<{ access_token: string; user?: { email: string; full_name?: string } }>('/auth/signin', { method: 'POST', body: data }),
    signout: () => request('/auth/signout', { method: 'POST' }),
    me: () => request<{ id: string; email: string; full_name?: string; subscription_tier?: string; is_admin?: boolean }>('/auth/me'),
  },

  brokers: {
    list: () => request('/brokers/list'),
    credentials: () => request('/brokers/credentials'),
    saveCredentials: (data: { broker: string; api_key: string; secret_key: string; additional_params?: Record<string, string> }) =>
      request('/brokers/credentials', { method: 'POST', body: data }),
    deleteCredentials: (broker: string) => request(`/brokers/credentials/${broker}`, { method: 'DELETE' }),
    fyersAuthUrl: () => request('/brokers/fyers/auth-url'),
    fyersExchangeCode: (authCode: string) => request('/brokers/fyers/exchange-code', { method: 'POST', body: { auth_code: authCode } }),
    fyersReAuth: () => request('/brokers/fyers/re-auth', { method: 'POST' }),
    activate: (broker: string) => request('/brokers/activate', { method: 'POST', body: { broker } }),
  },

  risk: {
    settings: () => request('/risk/settings'),
    update: (data: Record<string, unknown>) => request('/risk/settings', { method: 'POST', body: data }),
    enableKillSwitch: () => request('/risk/kill-switch/enable', { method: 'POST' }),
    disableKillSwitch: () => request('/risk/kill-switch/disable', { method: 'POST' }),
    killSwitchStatus: () => request('/risk/kill-switch'),
    enableLive: () => request('/risk/live/enable', { method: 'POST', body: { confirm: true } }),
    disableLive: () => request('/risk/live/disable'),
    liveStatus: () => request('/risk/live/status'),
  },

  strategies: {
    list: () => request('/strategies/'),
    listBuiltin: () => request('/strategies/list-builtin'),
    assigned: () => request('/strategies/assigned'),
    create: (data: { name: string; type: string; config: Record<string, unknown> }) =>
      request('/strategies/', { method: 'POST', body: data }),
    update: (id: string, data: Record<string, unknown>) => request(`/strategies/${id}`, { method: 'PUT', body: data }),
    delete: (id: string) => request(`/strategies/${id}`, { method: 'DELETE' }),
  },

  admin: {
    users: {
      list: () => request<{ users: AdminUser[] }>('/admin/users'),
      updateTier: (userId: string, data: { subscription_tier: string }) =>
        request<{ subscription_tier: string; message: string; deactivated_assignments: number }>(
          `/admin/users/${userId}`, { method: 'PATCH', body: data },
        ),
    },
    assignments: {
      list: (userId?: string) => request(userId ? `/admin/assignments?user_id=${userId}` : '/admin/assignments'),
      create: (data: { user_id: string; strategy_key: string }) =>
        request('/admin/assignments', { method: 'POST', body: data }),
      remove: (id: string) => request(`/admin/assignments/${id}`, { method: 'DELETE' }),
    },
    broadcast: {
      recipients: (strategyKey: string) =>
        request<{ recipients: { user_id: string; email: string; full_name: string }[] }>(
          `/admin/broadcast/recipients?strategy_key=${strategyKey}`,
        ),
      send: (data: {
        strategy_key: string; symbol: string; action: string; quantity: number;
        price?: number; exchange?: string; order_type?: string; product?: string;
        reason?: string; paper?: boolean;
      }) => request<{ results: { user_id: string; email: string; success: boolean; broker_order_id: string; message: string; status: string }[]; count: number; paper: boolean }>(
        '/admin/broadcast', { method: 'POST', body: data },
      ),
    },
  },

  engine: {
    start: (data: { strategy_id: string; broker: string; mode?: string; symbols?: string[] }) =>
      request('/engine/start', { method: 'POST', body: data }),
    stop: (runId: string) => request(`/engine/stop/${runId}`, { method: 'POST' }),
    trade: (data: {
      symbol: string; side: string; quantity: number; price?: number;
      exchange?: string; order_type?: string; product?: string;
      trigger_price?: number; strategy_id?: string;
      instrument_type?: string; strike_price?: number; expiry_date?: string; option_type?: string;
    }) => request('/engine/trade', { method: 'POST', body: data }),
    runs: () => request('/engine/runs'),
    orders: () => request('/engine/orders'),
    cancelOrder: (orderId: string) => request(`/engine/orders/${orderId}/cancel`, { method: 'POST' }),
    positions: () => request('/engine/positions'),
    funds: () => request('/engine/funds'),
  },

  ai: {
    desk: (command: string) => request('/ai/desk', { method: 'POST', body: { command } }),
    journal: (lookbackDays = 7) => request(`/ai/journal?lookback_days=${lookbackDays}`),
    journalEntries: () => request('/ai/journal/entries'),
  },

  marketdata: {
    startSimulator: () => request('/marketdata/simulator/start', { method: 'POST' }),
    stopSimulator: () => request('/marketdata/simulator/stop', { method: 'POST' }),
    symbols: () => request('/marketdata/symbols'),
    watchlist: () => request('/marketdata/watchlist'),
    optionChain: (symbol: string) => request(`/marketdata/option-chain?symbol=${symbol}`),
  },

  tradingview: {
    webhook: (data: Record<string, unknown>) => request('/tradingview/webhook', { method: 'POST', body: data }),
  },

  backtest: {
    run: (data: Record<string, unknown>) => request('/backtest/run', { method: 'POST', body: data }),
    strategies: () => request('/backtest/strategies'),
  },
}

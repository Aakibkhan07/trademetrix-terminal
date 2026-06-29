const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

let _token: string | null = null

export function setApiToken(t: string | null) {
  _token = t
}

interface ApiOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {} } = options

  const authHeaders: Record<string, string> = { ...headers }
  if (_token) {
    authHeaders['Authorization'] = `Bearer ${_token}`
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
    },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 204) return undefined as T

  const data = await res.json()

  if (!res.ok) {
    throw new Error(data.detail || `Request failed: ${res.status}`)
  }

  return data as T
}

export const api = {
  setToken: setApiToken,

  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  auth: {
    signup: (data: { email: string; password: string; full_name?: string }) =>
      request<{ access_token: string; user?: { email: string; full_name?: string } }>('/auth/signup', { method: 'POST', body: data }),
    signin: (data: { email: string; password: string }) =>
      request<{ access_token: string; user?: { email: string; full_name?: string } }>('/auth/signin', { method: 'POST', body: data }),
    signout: () => request('/auth/signout', { method: 'POST' }),
    me: () => request('/auth/me'),
  },

  brokers: {
    list: () => request('/brokers/list'),
    credentials: () => request('/brokers/credentials'),
    saveCredentials: (data: { broker: string; api_key: string; secret_key: string }) =>
      request('/brokers/credentials', { method: 'POST', body: data }),
    deleteCredentials: (broker: string) => request(`/brokers/credentials/${broker}`, { method: 'DELETE' }),
  },

  risk: {
    settings: () => request('/risk/settings'),
    update: (data: Record<string, unknown>) => request('/risk/settings', { method: 'POST', body: data }),
    enableKillSwitch: () => request('/risk/kill-switch/enable', { method: 'POST' }),
    disableKillSwitch: () => request('/risk/kill-switch/disable', { method: 'POST' }),
    killSwitchStatus: () => request('/risk/kill-switch'),
    enableLive: () => request('/risk/live/enable'),
    disableLive: () => request('/risk/live/disable'),
    liveStatus: () => request('/risk/live/status'),
  },

  strategies: {
    list: () => request('/strategies/'),
    listBuiltin: () => request('/strategies/list-builtin'),
    create: (data: { name: string; type: string; config: Record<string, unknown> }) =>
      request('/strategies/', { method: 'POST', body: data }),
    update: (id: string, data: Record<string, unknown>) => request(`/strategies/${id}`, { method: 'PUT', body: data }),
    delete: (id: string) => request(`/strategies/${id}`, { method: 'DELETE' }),
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
  },

  backtest: {
    run: (data: Record<string, unknown>) => request('/backtest/run', { method: 'POST', body: data }),
    strategies: () => request('/backtest/strategies'),
  },
}

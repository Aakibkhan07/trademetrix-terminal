const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

interface ApiOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {} } = options

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
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
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  auth: {
    signup: (data: { email: string; password: string; full_name?: string }) =>
      api.post('/auth/signup', data),
    signin: (data: { email: string; password: string }) =>
      api.post('/auth/signin', data),
    signout: () => api.post('/auth/signout'),
    me: () => api.get('/auth/me'),
  },

  brokers: {
    list: () => api.get('/brokers/list'),
    credentials: () => api.get('/brokers/credentials'),
    saveCredentials: (data: { broker: string; api_key: string; secret_key: string }) =>
      api.post('/brokers/credentials', data),
    deleteCredentials: (broker: string) => api.delete(`/brokers/credentials/${broker}`),
  },

  risk: {
    settings: () => api.get('/risk/settings'),
    update: (data: Record<string, unknown>) => api.post('/risk/settings', data),
    enableKillSwitch: () => api.post('/risk/kill-switch/enable'),
    disableKillSwitch: () => api.post('/risk/kill-switch/disable'),
    killSwitchStatus: () => api.get('/risk/kill-switch'),
    enableLive: () => api.post('/risk/live/enable'),
    disableLive: () => api.post('/risk/live/disable'),
    liveStatus: () => api.get('/risk/live/status'),
  },

  strategies: {
    list: () => api.get('/strategies/'),
    listBuiltin: () => api.get('/strategies/list-builtin'),
    create: (data: { name: string; type: string; config: Record<string, unknown> }) =>
      api.post('/strategies/', data),
    update: (id: string, data: Record<string, unknown>) => api.put(`/strategies/${id}`, data),
    delete: (id: string) => api.delete(`/strategies/${id}`),
  },

  engine: {
    start: (data: { strategy_id: string; broker: string; mode?: string; symbols?: string[] }) =>
      api.post('/engine/start', data),
    stop: (runId: string) => api.post(`/engine/stop/${runId}`),
    trade: (data: { symbol: string; side: string; quantity: number; price?: number; strategy_id?: string }) =>
      api.post('/engine/trade', data),
    runs: () => api.get('/engine/runs'),
  },

  ai: {
    desk: (command: string) => api.post('/ai/desk', { command }),
    journal: (lookbackDays = 7) => api.get(`/ai/journal?lookback_days=${lookbackDays}`),
    journalEntries: () => api.get('/ai/journal/entries'),
  },

  marketdata: {
    startSimulator: () => api.post('/marketdata/simulator/start'),
    stopSimulator: () => api.post('/marketdata/simulator/stop'),
    symbols: () => api.get('/marketdata/symbols'),
  },

  backtest: {
    run: (data: Record<string, unknown>) => api.post('/backtest/run', data),
    strategies: () => api.get('/backtest/strategies'),
  },
}

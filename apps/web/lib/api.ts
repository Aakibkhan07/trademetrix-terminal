const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export interface BrokerFieldMeta {
  key: string
  label: string
  type?: string
  placeholder?: string
  required: boolean
}

export interface BrokerMeta {
  broker: string
  display_name: string
  auth_type: string
  description: string
  fields: BrokerFieldMeta[]
  has_additional_params: boolean
  additional_params_fields?: BrokerFieldMeta[]
  instructions: string
  oauth_available: boolean
}

export interface AdminUser {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  role: string
  subscription_tier: string
  active_assignments: number
  max_active_strategies: number
}

export interface AdminRiskSetting {
  user_id: string
  email: string
  full_name: string
  max_capital: number
  max_position_size: number
  max_open_positions: number
  max_daily_loss: number
  max_drawdown_pct: number
  kill_switch_enabled: boolean
  is_live: boolean
  strategy_id: string
}

export interface AdminBroker {
  id: string
  user_id: string
  email: string
  full_name: string
  broker: string
  is_active: boolean
  has_access_token: boolean
  created_at: string
  updated_at: string
}

export interface AdminOrder {
  id: string
  user_id: string
  email: string
  full_name: string
  broker: string
  broker_order_id: string
  symbol: string
  exchange: string
  side: string
  order_type: string
  product: string
  quantity: number
  price: number
  status: string
  is_paper: boolean
  message: string
  filled_quantity: number
  filled_at: string
  created_at: string
}

export interface AdminAuditEntry {
  id: string
  user_id: string
  action: string
  resource: string
  resource_id: string
  details: Record<string, unknown> | null
  created_at: string
}

export interface AdminStats {
  total_users: number
  total_admins: number
  active_assignments: number
  total_strategies: number
  tier_distribution: Record<string, number>
}

export interface Alert {
  id: string
  symbol: string
  condition: string
  target_price: number
  is_active: boolean
  triggered_at: string | null
  note: string
  created_at: string
}

export interface JournalNote {
  id: string
  user_id: string
  entry_type: string
  content: string
  tags: string[]
  trade_ids: string[]
  created_at: string
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

let _csrfBootstrapped = false

async function _ensureCSRF(): Promise<void> {
  if (_csrfBootstrapped) return
  _csrfBootstrapped = true
  if (getCSRFToken()) return
  await fetch(`${API_BASE}/auth/csrf`, { credentials: 'include' })
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, signal } = options

  const finalHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...headers,
  }

  if (method !== 'GET') {
    await _ensureCSRF()
    const csrf = getCSRFToken()
    if (!csrf) {
      throw new ApiError(0, 'CSRF token not available — refresh or sign in again')
    }
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
    me: () => request<{ id: string; email: string; full_name?: string; phone?: string; subscription_tier?: string; is_admin?: boolean }>('/auth/me'),
    sendOTP: (data: { email: string; phone?: string }) =>
      request<{ message: string; exists: boolean }>('/auth/send-otp', { method: 'POST', body: data }),
    registerWithOTP: (data: { email: string; password: string; full_name?: string; phone?: string }) =>
      request<{ message: string; user_id: string }>('/auth/register-with-otp', { method: 'POST', body: data }),
    verifyOTP: (data: { email: string; otp: string }) =>
      request<{ access_token: string; user: { id: string; email: string; full_name?: string; phone?: string; subscription_tier?: string }; is_new: boolean }>('/auth/verify-otp', { method: 'POST', body: data }),
  },

  brokers: {
    list: () => request('/brokers/list'),
    metadata: () => request<{ brokers: BrokerMeta[] }>('/brokers/metadata'),
    credentials: () => request('/brokers/credentials'),
    saveCredentials: (data: {
      broker: string;
      api_key?: string;
      secret_key?: string;
      client_id?: string;
      client_code?: string;
      access_token?: string;
      additional_params?: Record<string, string>;
    }) => request('/brokers/credentials', { method: 'POST', body: data }),
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
    fetch: <T>(path: string) => request<T>('/admin' + path),
    brokers: () => request<{ brokers: AdminBroker[] }>('/admin/brokers'),
    orders: (params?: { user_id?: string; is_paper?: string; limit?: number; offset?: number }) =>
      request<{ orders: AdminOrder[]; count: number }>('/admin/orders' + (params ? '?' + new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)]))
      ).toString() : '')),
    auditLog: (params?: { user_id?: string; action?: string; limit?: number; offset?: number }) =>
      request<{ entries: AdminAuditEntry[]; count: number }>('/admin/audit-log' + (params ? '?' + new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)]))
      ).toString() : '')),
    stats: () => request<AdminStats>('/admin/stats'),
    risk: () => request<{ settings: AdminRiskSetting[]; count: number }>('/admin/risk'),
    activeBrokers: () => request<{ active_broker_count: number; oauthed_count: number }>('/admin/active-brokers'),
    admins: {
      list: () => request<{ admins: { id: string; email: string; full_name: string; is_admin: boolean; role: string }[] }>('/admin/admins'),
      create: (data: { email: string; role: string }) =>
        request<{ message: string }>('/admin/admins', { method: 'POST', body: data }),
      updateRole: (userId: string, data: { role: string }) =>
        request<{ message: string }>(`/admin/admins/${userId}`, { method: 'PATCH', body: data }),
      remove: (userId: string) =>
        request<{ message: string }>(`/admin/admins/${userId}`, { method: 'DELETE' }),
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
    copilot: (messages: { role: string; content: string }[]) =>
      request<{ response: string }>('/ai/copilot', { method: 'POST', body: { messages } }),
  },

  marketdata: {
    startSimulator: () => request('/marketdata/simulator/start', { method: 'POST' }),
    stopSimulator: () => request('/marketdata/simulator/stop', { method: 'POST' }),
    startFeed: () => request('/marketdata/feed/start', { method: 'POST' }),
    stopFeed: () => request('/marketdata/feed/stop', { method: 'POST' }),
    symbols: () => request('/marketdata/symbols'),
    watchlist: () => request('/marketdata/watchlist'),
    optionChain: (symbol: string) => request(`/marketdata/option-chain?symbol=${symbol}`),
    historical: (symbol: string, interval = '15m', days = 7) =>
      request(`/marketdata/historical?symbol=${symbol}&interval=${interval}&days=${days}`),
  },

  alerts: {
    list: () => request<{ alerts: Alert[] }>('/alerts/'),
    create: (data: { symbol: string; condition: string; target_price: number; note?: string }) =>
      request<Alert>('/alerts/', { method: 'POST', body: data }),
    remove: (id: string) => request(`/alerts/${id}`, { method: 'DELETE' }),
    toggle: (id: string) => request<{ is_active: boolean }>(`/alerts/${id}/toggle`, { method: 'POST' }),
    getNotificationPrefs: () => request<{ channels: string[] }>('/alerts/notification-prefs'),
    updateNotificationPrefs: (channels: string[]) =>
      request('/alerts/notification-prefs', { method: 'PUT', body: { channels } }),
  },

  journal: {
    addOrderNote: (orderId: string, data: { note: string; tags?: string[] }) =>
      request(`/engine/orders/${orderId}/note`, { method: 'POST', body: data }),
    getOrderNotes: () => request<{ notes: JournalNote[] }>('/engine/orders/notes'),
  },

  tradingview: {
    webhook: (data: Record<string, unknown>) => request('/tradingview/webhook', { method: 'POST', body: data }),
  },

  backtest: {
    run: (data: Record<string, unknown>) => request('/backtest/run', { method: 'POST', body: data }),
    strategies: () => request('/backtest/strategies'),
  },

  builder: {
    blocks: (category?: string) => request(category ? `/builder/blocks?category=${category}` : '/builder/blocks'),
    categories: () => request('/builder/blocks/categories'),
    getBlock: (blockType: string) => request(`/builder/blocks/${blockType}`),
    create: (data: { name?: string; description?: string; template?: string }) =>
      request('/builder/strategies', { method: 'POST', body: data }),
    list: (status?: string) => request(status ? `/builder/strategies?status=${status}` : '/builder/strategies'),
    get: (id: string) => request(`/builder/strategies/${id}`),
    update: (id: string, data: Record<string, unknown>) => request(`/builder/strategies/${id}`, { method: 'PUT', body: data }),
    delete: (id: string) => request(`/builder/strategies/${id}`, { method: 'DELETE' }),
    compile: (id: string) => request(`/builder/strategies/${id}/compile`, { method: 'POST' }),
    validate: (id: string) => request(`/builder/strategies/${id}/validate`, { method: 'POST' }),
    preview: (id: string) => request(`/builder/strategies/${id}/preview`),
    publish: (id: string) => request(`/builder/strategies/${id}/publish`, { method: 'POST' }),
    archive: (id: string) => request(`/builder/strategies/${id}/archive`, { method: 'POST' }),
    clone: (id: string) => request(`/builder/strategies/${id}/clone`, { method: 'POST' }),
    rollback: (id: string, version: number) => request(`/builder/strategies/${id}/rollback/${version}`, { method: 'POST' }),
    versions: (id: string) => request(`/builder/strategies/${id}/versions`),
    templates: () => request('/builder/templates'),
    getTemplate: (key: string) => request(`/builder/templates/${key}`),
    import: (data: Record<string, unknown>) => request('/builder/import', { method: 'POST', body: data }),
    export: (id: string, format?: string) => request(`/builder/strategies/${id}/export${format ? `?format=${format}` : ''}`),
  },

  userStrategies: {
    list: (statusFilter?: string) =>
      request(statusFilter ? `/user-strategies/?status_filter=${statusFilter}` : '/user-strategies/'),
    create: (data: Record<string, unknown>) => request('/user-strategies/', { method: 'POST', body: data }),
    get: (id: string) => request(`/user-strategies/${id}`),
    update: (id: string, data: Record<string, unknown>) => request(`/user-strategies/${id}`, { method: 'PATCH', body: data }),
    delete: (id: string) => request(`/user-strategies/${id}`, { method: 'DELETE' }),
    deploy: (id: string, mode: string) => request(`/user-strategies/${id}/deploy`, { method: 'POST', body: { mode } }),
  },

  marginEstimate: (data: { index_symbol: string; legs: Record<string, unknown>[]; broker?: string }) =>
    request('/margin-estimate/', { method: 'POST', body: data }),

  events: {
    stream: () => `${API_BASE}/events/stream`,
  },
}

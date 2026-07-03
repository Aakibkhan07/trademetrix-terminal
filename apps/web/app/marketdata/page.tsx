'use client'

import { useEffect, useState, useCallback } from 'react'
import { useMarketData } from '@/lib/use-market-data'
import { useToast } from '@/lib/use-toast'
import { api } from '@/lib/api'
import Chart from '@/components/chart'

type WatchItem = { symbol: string; name: string; type: string }

const STORAGE_KEY = 'tm_watchlist_custom'

function loadCustomWatchlist(): WatchItem[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}
function saveCustomWatchlist(items: WatchItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
}

interface PriceAlert {
  id: string
  symbol: string
  name: string
  target: number
  direction: 'above' | 'below'
  triggered: boolean
  triggeredAt?: string
  backendId?: string
}

const ALL_SYMBOLS: WatchItem[] = [
  { symbol: 'NSE:NIFTY50-INDEX', name: 'NIFTY 50', type: 'index' },
  { symbol: 'NSE:BANKNIFTY-INDEX', name: 'BANK NIFTY', type: 'index' },
  { symbol: 'NSE:FINNIFTY-INDEX', name: 'FIN NIFTY', type: 'index' },
  { symbol: 'NSE:SENSEX-INDEX', name: 'SENSEX', type: 'index' },
  { symbol: 'NSE:INDIAVIX-INDEX', name: 'INDIA VIX', type: 'index' },
  { symbol: 'NSE:NIFTYIT-INDEX', name: 'NIFTY IT', type: 'index' },
  { symbol: 'NSE:NIFTYAUTO-INDEX', name: 'NIFTY AUTO', type: 'index' },
  { symbol: 'NSE:NIFTYPHARMA-INDEX', name: 'NIFTY PHARMA', type: 'index' },
  { symbol: 'BSE:RELIANCE', name: 'Reliance Industries', type: 'stock' },
  { symbol: 'BSE:TCS', name: 'Tata Consultancy Services', type: 'stock' },
  { symbol: 'BSE:HDFCBANK', name: 'HDFC Bank', type: 'stock' },
  { symbol: 'BSE:INFY', name: 'Infosys', type: 'stock' },
  { symbol: 'BSE:ICICIBANK', name: 'ICICI Bank', type: 'stock' },
  { symbol: 'BSE:SBIN', name: 'State Bank of India', type: 'stock' },
  { symbol: 'BSE:BAJFINANCE', name: 'Bajaj Finance', type: 'stock' },
  { symbol: 'BSE:BHARTIARTL', name: 'Bharti Airtel', type: 'stock' },
  { symbol: 'BSE:KOTAKBANK', name: 'Kotak Mahindra Bank', type: 'stock' },
  { symbol: 'BSE:LT', name: 'Larsen & Toubro', type: 'stock' },
  { symbol: 'BSE:WIPRO', name: 'Wipro', type: 'stock' },
  { symbol: 'BSE:HCLTECH', name: 'HCL Technologies', type: 'stock' },
  { symbol: 'BSE:MARUTI', name: 'Maruti Suzuki', type: 'stock' },
  { symbol: 'BSE:ITC', name: 'ITC', type: 'stock' },
  { symbol: 'BSE:TITAN', name: 'Titan Company', type: 'stock' },
  { symbol: 'BSE:ASIANPAINT', name: 'Asian Paints', type: 'stock' },
  { symbol: 'BSE:NTPC', name: 'NTPC', type: 'stock' },
  { symbol: 'BSE:POWERGRID', name: 'Power Grid Corporation', type: 'stock' },
  { symbol: 'BSE:ULTRACEMCO', name: 'UltraTech Cement', type: 'stock' },
  { symbol: 'BSE:AXISBANK', name: 'Axis Bank', type: 'stock' },
  { symbol: 'BSE:M&M', name: 'Mahindra & Mahindra', type: 'stock' },
  { symbol: 'BSE:SUNPHARMA', name: 'Sun Pharmaceutical', type: 'stock' },
]

export default function MarketDataPage() {
  const { ticks, connected, feedMode, subscribe, startFeed, stopFeed } = useMarketData()
  const { toast } = useToast()
  const [feedOn, setFeedOn] = useState(false)
  const [apiIndices, setApiIndices] = useState<WatchItem[]>([])
  const [apiStocks, setApiStocks] = useState<WatchItem[]>([])
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'indices' | 'stocks'>('all')
  const [chartSymbol, setChartSymbol] = useState('NSE:NIFTY50-INDEX')
  const [customItems, setCustomItems] = useState<WatchItem[]>([])
  const [showAddModal, setShowAddModal] = useState(false)
  const [addSearch, setAddSearch] = useState('')
  const [alerts, setAlerts] = useState<PriceAlert[]>([])
  const [showAlertModal, setShowAlertModal] = useState(false)
  const [alertSymbol, setAlertSymbol] = useState('')
  const [alertName, setAlertName] = useState('')
  const [alertTarget, setAlertTarget] = useState(0)
  const [alertDirection, setAlertDirection] = useState<'above' | 'below'>('above')

  const loadAlertsFromApi = useCallback(async () => {
    try {
      const data = await api.alerts.list()
      const mapped: PriceAlert[] = (data.alerts || []).map(a => ({
        id: a.id,
        symbol: a.symbol,
        name: a.note || a.symbol,
        target: a.target_price,
        direction: (a.condition === 'below' ? 'below' : 'above') as 'above' | 'below',
        triggered: !!a.triggered_at,
        triggeredAt: a.triggered_at || undefined,
        backendId: a.id,
      }))
      setAlerts(mapped)
    } catch {
      setAlerts([])
    }
  }, [])

  useEffect(() => {
    setCustomItems(loadCustomWatchlist())
    loadAlertsFromApi()
  }, [loadAlertsFromApi])

  useEffect(() => {
    const interval = setInterval(async () => {
      setAlerts(prev => {
        let changed = false
        const updated = prev.map(a => {
          if (a.triggered) return a
          const t = ticks[a.symbol]
          if (!t?.last_price) return a
          const price = t.last_price
          if ((a.direction === 'above' && price >= a.target) || (a.direction === 'below' && price <= a.target)) {
            changed = true
            if (a.backendId) {
              api.alerts.toggle(a.backendId).catch(() => {})
            }
            toast('info', `Alert: ${a.name || a.symbol} ${a.direction === 'above' ? 'crossed above' : 'dropped below'} \u20B9${a.target} (current: \u20B9${price})`)
            return { ...a, triggered: true, triggeredAt: new Date().toISOString() }
          }
          return a
        })
        return changed ? updated : prev
      })
    }, 2000)
    return () => clearInterval(interval)
  }, [ticks, toast])

  const loadWatchlist = useCallback(async () => {
    try {
      const data = await api.marketdata.watchlist() as { indices: WatchItem[]; stocks: WatchItem[] }
      setApiIndices(data.indices || [])
      setApiStocks(data.stocks || [])
      const allSymbols = [...(data.indices || []), ...(data.stocks || []), ...customItems].map(i => i.symbol)
      subscribe(allSymbols)
    } catch {}
  }, [subscribe, customItems])

  useEffect(() => { loadWatchlist() }, [loadWatchlist])

  const toggleFeed = async () => {
    if (feedOn) { await stopFeed(); setFeedOn(false) }
    else { await startFeed(); setFeedOn(true) }
  }

  const allItems = [...apiIndices, ...apiStocks, ...customItems]
  const items = activeTab === 'indices' ? allItems.filter(i => i.type === 'index') : activeTab === 'stocks' ? allItems.filter(i => i.type === 'stock') : allItems
  const filtered = search
    ? items.filter(i => i.name.toLowerCase().includes(search.toLowerCase()) || i.symbol.toLowerCase().includes(search.toLowerCase()))
    : items

  const sortedTicks = Object.values(ticks).sort((a, b) => Math.abs(b.change_pct ?? 0) - Math.abs(a.change_pct ?? 0))

  const timeframes = ['1D', '1W', '1M', '3M', '1Y']
  const [chartTF, setChartTF] = useState('1D')

  const addToWatchlist = (item: WatchItem) => {
    if (customItems.some(c => c.symbol === item.symbol)) return
    const updated = [...customItems, item]
    setCustomItems(updated)
    saveCustomWatchlist(updated)
    subscribe([item.symbol])
    toast('success', `Added ${item.name} to watchlist`)
  }

  const removeFromWatchlist = (symbol: string) => {
    const updated = customItems.filter(c => c.symbol !== symbol)
    setCustomItems(updated)
    saveCustomWatchlist(updated)
    toast('info', 'Removed from watchlist')
  }

  const addableSymbols = ALL_SYMBOLS.filter(s =>
    !allItems.some(c => c.symbol === s.symbol) &&
    (s.name.toLowerCase().includes(addSearch.toLowerCase()) || s.symbol.toLowerCase().includes(addSearch.toLowerCase()))
  )

  const openAlert = (symbol: string, name: string) => {
    setAlertSymbol(symbol)
    setAlertName(name)
    setAlertTarget(ticks[symbol]?.last_price || 0)
    setAlertDirection('above')
    setShowAlertModal(true)
  }

  const createAlert = async () => {
    try {
      const result = await api.alerts.create({
        symbol: alertSymbol,
        condition: alertDirection,
        target_price: alertTarget,
        note: alertName,
      })
      const alert: PriceAlert = {
        id: result.id,
        symbol: alertSymbol,
        name: alertName,
        target: alertTarget,
        direction: alertDirection,
        triggered: false,
        backendId: result.id,
      }
      setAlerts(prev => [...prev, alert])
      setShowAlertModal(false)
      toast('success', `Alert set: ${alertName} ${alertDirection === 'above' ? '>' : '<'} \u20B9${alertTarget}`)
    } catch {
      toast('error', 'Failed to create alert')
    }
  }

  const removeAlert = async (id: string) => {
    const alert = alerts.find(a => a.id === id)
    setAlerts(prev => prev.filter(a => a.id !== id))
    if (alert?.backendId) {
      try { await api.alerts.remove(alert.backendId) } catch {}
    }
  }

  const isCustom = (symbol: string) => customItems.some(c => c.symbol === symbol)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="t-row" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>Market Data</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2, fontSize: 12 }}>
            <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} />
            <span className={connected ? 't-up' : 't-down'}>{connected ? 'Connected' : 'Disconnected'}</span>
            <span className="t-faint">&middot;</span>
            <span className="t-sub">{Object.keys(ticks).length} symbols</span>
            {feedMode === 'simulator' && (
              <span className="t-badge t-badge-amber">SIMULATED</span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => setShowAddModal(true)}>
            + Add Symbol
          </button>
          <button className={`t-btn t-btn-sm ${feedOn ? 't-btn-ghost' : 't-btn-primary'}`} onClick={toggleFeed}>
            {feedOn ? 'Stop Feed' : 'Start Feed'}
          </button>
        </div>
      </div>

      {/* Active Alerts Bar */}
      {alerts.filter(a => !a.triggered).length > 0 && (
        <div className="t-panel" style={{ padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="t-faint" style={{ fontSize: 10, fontWeight: 600 }}>ACTIVE ALERTS</span>
          {alerts.filter(a => !a.triggered).map(a => (
            <span key={a.id} className="t-chip active" style={{ fontSize: 10 }}>
              {a.name || a.symbol} {a.direction === 'above' ? '>' : '<'} \u20B9{a.target}
              <span style={{ marginLeft: 4, cursor: 'pointer', opacity: 0.5 }} onClick={() => removeAlert(a.id)}>x</span>
            </span>
          ))}
        </div>
      )}

      {/* Top Movers */}
      {sortedTicks.length > 0 && (
        <div className="t-grid-2" style={{ gap: 8 }}>
          {sortedTicks.slice(0, 8).map((t) => {
            const pct = t.change_pct ?? 0
            const item = allItems.find(i => i.symbol === t.symbol)
            return (
              <div key={t.symbol} className="t-panel" style={{ padding: '10px 14px' }}>
                <div className="t-panel-body" style={{ padding: 0 }}>
                  <div className="t-faint" style={{ fontSize: 11, marginBottom: 2 }}>{item?.name || t.symbol?.split(':').pop()}</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span className="t-num" style={{ fontSize: 18 }}>{t.last_price?.toFixed(1)}</span>
                    <span className={`t-num ${pct >= 0 ? 't-up' : 't-down'}`} style={{ fontSize: 12 }}>
                      {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Chart */}
      <div className="t-chart-box">
        <div className="t-chart-controls">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="t-panel-title" style={{ fontSize: 13, fontWeight: 600 }}>{chartSymbol}</span>
            <span className="t-dot t-dot-green t-dot-pulse" />
          </div>
          <div style={{ display: 'flex', gap: 2 }}>
            {timeframes.map(tf => (
              <button key={tf} className={`t-chart-btn ${chartTF === tf ? 'active' : ''}`} onClick={() => setChartTF(tf)}>
                {tf}
              </button>
            ))}
          </div>
        </div>
        <div className="t-chart-area">
          <Chart symbol={chartSymbol} height={320} />
        </div>
      </div>

      {/* Search */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input className="t-input" placeholder="Search symbols..." value={search}
          onChange={(e) => setSearch(e.target.value)} style={{ flex: 1 }} />
        <span className="t-faint" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
          {filtered.length} symbols
        </span>
      </div>

      {/* Tabs */}
      <div className="t-tabs">
        <button className={`t-tab ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          All <span className="t-badge t-badge-sub">{allItems.length}</span>
        </button>
        <button className={`t-tab ${activeTab === 'indices' ? 'active' : ''}`} onClick={() => setActiveTab('indices')}>
          Indices <span className="t-badge t-badge-violet">{allItems.filter(i => i.type === 'index').length}</span>
        </button>
        <button className={`t-tab ${activeTab === 'stocks' ? 'active' : ''}`} onClick={() => setActiveTab('stocks')}>
          Stocks <span className="t-badge t-badge-cyan">{allItems.filter(i => i.type === 'stock').length}</span>
        </button>
      </div>

      {/* Live Ticks Table */}
      <div className="t-panel" style={{ padding: 0 }}>
        <div className="t-panel-header">
          <h3 className="t-panel-title">
            Live Ticks
            <span className={`t-dot ${connected ? 't-dot-green t-dot-pulse' : 't-dot-red'}`} style={{ marginLeft: 8 }} />
          </h3>
        </div>
        {filtered.length > 0 ? (
          <div className="t-table-wrap">
            <table className="t-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>LTP</th>
                  <th>Change</th>
                  <th>Change%</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Volume</th>
                  <th>OI</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const t = ticks[item.symbol]
                  const chg = t?.change ?? 0
                  const pct = t?.change_pct ?? 0
                  return (
                    <tr key={item.symbol} style={{ cursor: 'pointer' }}
                      onClick={() => setChartSymbol(item.symbol)}>
                      <td style={{
                        fontWeight: 600,
                        fontSize: 10,
                        color: chartSymbol === item.symbol ? 'var(--cyan)' : undefined
                      }}>
                        {item.symbol}
                      </td>
                      <td>{item.name}</td>
                      <td>
                        <span className={`t-badge ${item.type === 'index' ? 't-badge-violet' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>
                          {item.type}
                        </span>
                      </td>
                      <td><span className="t-num">{t?.last_price?.toFixed(1) || '-'}</span></td>
                      <td>
                        <span className={`t-num ${chg >= 0 ? 't-up' : 't-down'}`}>
                          {t ? `${chg >= 0 ? '+' : ''}${chg?.toFixed(1)}` : '-'}
                        </span>
                      </td>
                      <td>
                        <span className={`t-num ${pct >= 0 ? 't-up' : 't-down'}`}>
                          {t ? `${pct >= 0 ? '+' : ''}${pct?.toFixed(2)}%` : '-'}
                        </span>
                      </td>
                      <td><span className="t-num t-up">{t?.bid || '-'}</span></td>
                      <td><span className="t-num t-down">{t?.ask || '-'}</span></td>
                      <td><span className="t-num t-faint">{t?.volume ? t.volume.toLocaleString() : '-'}</span></td>
                      <td><span className="t-num t-faint">{t?.oi ? t.oi.toLocaleString() : '-'}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 2 }}>
                          <button className="t-btn t-btn-xs t-btn-ghost" title="Set Alert"
                            onClick={(e) => { e.stopPropagation(); openAlert(item.symbol, item.name) }}>
                            Bell
                          </button>
                          {isCustom(item.symbol) && (
                            <button className="t-btn t-btn-xs t-btn-ghost" title="Remove from watchlist"
                              onClick={(e) => { e.stopPropagation(); removeFromWatchlist(item.symbol) }}
                              style={{ color: 'var(--text-red)' }}>
                              x
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="t-panel-body" style={{ textAlign: 'center' }}>
            <span className="t-faint">{search ? 'No matches found' : 'Loading symbols...'}</span>
          </div>
        )}
      </div>

      {/* Add Symbol Modal */}
      {showAddModal && (
        <div className="t-modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="t-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <h3 className="t-modal-title" style={{ marginBottom: 12 }}>Add Symbol</h3>
            <input className="t-input" placeholder="Search symbols..." value={addSearch}
              onChange={e => setAddSearch(e.target.value)} autoFocus style={{ marginBottom: 12 }} />
            <div style={{ maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
              {addableSymbols.length === 0 ? (
                <span className="t-faint" style={{ padding: 12, textAlign: 'center' }}>No symbols found</span>
              ) : addableSymbols.slice(0, 30).map(s => (
                <div key={s.symbol} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 8px', borderRadius: 4, cursor: 'pointer',
                }}
                  className="t-hover-bg"
                  onClick={() => addToWatchlist(s)}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{s.name}</div>
                    <div className="t-faint" style={{ fontSize: 10 }}>{s.symbol}</div>
                  </div>
                  <span className={`t-badge ${s.type === 'index' ? 't-badge-violet' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>
                    {s.type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Alert Modal */}
      {showAlertModal && (
        <div className="t-modal-overlay" onClick={() => setShowAlertModal(false)}>
          <div className="t-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 360 }}>
            <h3 className="t-modal-title" style={{ marginBottom: 12 }}>Set Price Alert</h3>
            <p style={{ fontSize: 12, marginBottom: 12 }}>
              <span style={{ fontWeight: 600 }}>{alertName}</span>
              <span className="t-faint" style={{ marginLeft: 6 }}>{alertSymbol}</span>
            </p>
            <div className="t-row" style={{ gap: 8, marginBottom: 12 }}>
              <div className="t-col">
                <label className="t-label">Condition</label>
                <select className="t-select" value={alertDirection}
                  onChange={e => setAlertDirection(e.target.value as 'above' | 'below')}>
                  <option value="above">Crosses Above</option>
                  <option value="below">Drops Below</option>
                </select>
              </div>
              <div className="t-col">
                <label className="t-label">Target Price</label>
                <input className="t-input" type="number" step={0.05} value={alertTarget}
                  onChange={e => setAlertTarget(Number(e.target.value))} />
              </div>
            </div>
            <div className="t-row" style={{ gap: 6 }}>
              <button className="t-btn t-btn-primary" onClick={createAlert} style={{ flex: 1 }}>
                Set Alert
              </button>
              <button className="t-btn t-btn-ghost" onClick={() => setShowAlertModal(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Alert History */}
      {alerts.filter(a => a.triggered).length > 0 && (
        <div className="t-panel" style={{ padding: 0 }}>
          <div className="t-panel-header">
            <h3 className="t-panel-title">Triggered Alerts</h3>
          </div>
          <div className="t-panel-body">
            {alerts.filter(a => a.triggered).map(a => (
              <div key={a.id} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)'
              }}>
                <div>
                  <span style={{ fontWeight: 600, fontSize: 12 }}>{a.name || a.symbol}</span>
                  <span className="t-faint" style={{ marginLeft: 8, fontSize: 11 }}>
                    {a.direction === 'above' ? '>' : '<'} \u20B9{a.target}
                  </span>
                </div>
                <button className="t-btn t-btn-xs t-btn-ghost" onClick={() => removeAlert(a.id)} style={{ color: 'var(--text-red)' }}>
                  Clear
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

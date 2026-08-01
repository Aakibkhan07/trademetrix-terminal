'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMarketData } from '@/lib/use-market-data'
import { useUIStore } from '@/lib/stores/ui-store'
import { useToast } from '@/lib/use-toast'
import { api } from '@/lib/api'
import WatchRow, { type WatchItem } from './watch-row'
import AlertModal from './alert-modal'

type GroupId = 'all' | 'intraday' | 'options' | 'stocks' | 'swing' | 'etf'

const GROUP_ORDER: GroupId[] = ['all', 'intraday', 'options', 'stocks', 'swing', 'etf']
const GROUPS_KEY = 'tm_watchlist_groups'
const FAVS_KEY = 'tm_watchlist_favs'
const SPARK_KEY = 'tm_ws_spark_cache'
const ROW_H = 42

const ALL_SYMBOLS: WatchItem[] = [
  { symbol: 'NSE:NIFTY50-INDEX', name: 'NIFTY 50', type: 'index' },
  { symbol: 'NSE:BANKNIFTY-INDEX', name: 'BANK NIFTY', type: 'index' },
  { symbol: 'NSE:FINNIFTY-INDEX', name: 'FIN NIFTY', type: 'index' },
  { symbol: 'NSE:SENSEX-INDEX', name: 'SENSEX', type: 'index' },
  { symbol: 'NSE:INDIAVIX-INDEX', name: 'INDIA VIX', type: 'index' },
  { symbol: 'NSE:NIFTYIT-INDEX', name: 'NIFTY IT', type: 'index' },
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

interface WatchlistPanelProps {
  activeSymbol: string
  onSelectSymbol: (symbol: string, name: string) => void
  onAnalyze: (symbol: string, name: string) => void
}

function loadGroups(): Record<Exclude<GroupId, 'all'>, WatchItem[]> {
  try {
    const parsed = JSON.parse(localStorage.getItem(GROUPS_KEY) || '{}')
    return {
      intraday: Array.isArray(parsed.intraday) ? parsed.intraday : [],
      options: Array.isArray(parsed.options) ? parsed.options : [],
      stocks: Array.isArray(parsed.stocks) ? parsed.stocks : [],
      swing: Array.isArray(parsed.swing) ? parsed.swing : [],
      etf: Array.isArray(parsed.etf) ? parsed.etf : [],
    }
  } catch {
    return { intraday: [], options: [], stocks: [], swing: [], etf: [] }
  }
}

function loadFavs(): string[] {
  try { return JSON.parse(localStorage.getItem(FAVS_KEY) || '[]') } catch { return [] }
}

export default function WatchlistPanel({ activeSymbol, onSelectSymbol, onAnalyze }: WatchlistPanelProps) {
  const { ticks, subscribe } = useMarketData()
  const openQuickOrder = useUIStore(s => s.openQuickOrder)
  const { toast } = useToast()

  const [groups, setGroups] = useState<Record<Exclude<GroupId, 'all'>, WatchItem[]>>({ intraday: [], options: [], stocks: [], swing: [], etf: [] })
  const [seeded, setSeeded] = useState(false)
  const [favs, setFavs] = useState<string[]>([])
  const [group, setGroup] = useState<GroupId>('all')
  const [search, setSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [addSearch, setAddSearch] = useState('')
  const [freeText, setFreeText] = useState('')
  const [alertItem, setAlertItem] = useState<WatchItem | null>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportH, setViewportH] = useState(600)
  const sparksRef = useRef<Record<string, number[]>>({})
  const [, setSparkVersion] = useState(0)

  useEffect(() => {
    const favs = loadFavs()
    setFavs(favs)
    const groups = loadGroups()
    setGroups(groups)
    if (!groups.intraday.length) {
      api.marketdata.watchlist().then(d => {
        const data = d as { indices: WatchItem[]; stocks: WatchItem[] }
        const apiItems = [...(data.indices || []), ...(data.stocks || [])]
        const merged = { ...loadGroups(), intraday: apiItems, stocks: data.stocks || [] }
        setGroups(merged)
        localStorage.setItem(GROUPS_KEY, JSON.stringify(merged))
      }).catch(() => {})
    }
    setSeeded(true)
  }, [])

  const allItems = useMemo(() => {
    const seen = new Set<string>()
    return (Object.values(groups) as WatchItem[][]).flat().filter(i => {
      if (seen.has(i.symbol)) return false
      seen.add(i.symbol)
      return true
    })
  }, [groups])

  useEffect(() => {
    subscribe(allItems.map(i => i.symbol))
  }, [subscribe, allItems])

  const visibleItems = useMemo(() => {
    let items: WatchItem[]
    if (group === 'all') items = allItems
    else items = groups[group]
    const favSet = new Set(favs)
    items = [...items].sort((a, b) => (favSet.has(b.symbol) ? 1 : 0) - (favSet.has(a.symbol) ? 1 : 0))
    if (search) {
      const q = search.toLowerCase()
      items = items.filter(i => i.name.toLowerCase().includes(q) || i.symbol.toLowerCase().includes(q))
    }
    return items
  }, [allItems, groups, group, favs, search])

  useEffect(() => {
    const el = document.getElementById('ws-watch-scroll')
    if (el) {
      setViewportH(el.clientHeight)
      const onScroll = () => setScrollTop(el.scrollTop)
      el.addEventListener('scroll', onScroll, { passive: true })
      const ro = new ResizeObserver(() => setViewportH(el.clientHeight))
      ro.observe(el)
      return () => { el.removeEventListener('scroll', onScroll); ro.disconnect() }
    }
  }, [])

  const { start, end, padTop, padBottom } = useMemo(() => {
    const total = visibleItems.length
    const start = Math.max(0, Math.floor(scrollTop / ROW_H) - 4)
    const end = Math.min(total, Math.ceil((scrollTop + viewportH) / ROW_H) + 4)
    return { start, end, padTop: start * ROW_H, padBottom: (total - end) * ROW_H }
  }, [visibleItems.length, scrollTop, viewportH])

  useEffect(() => {
    const toFetch = visibleItems.slice(start, end).filter(i => !sparksRef.current[i.symbol])
    if (!toFetch.length) return
    let cancelled = false
    ;(async () => {
      for (const item of toFetch) {
        if (cancelled) break
        try {
          const raw = item.symbol.replace(/^NSE:/, '')
          const data = await api.marketdata.historical(raw, '5m', 1) as { candles: { close: number }[] }
          const closes = (data.candles || []).map(c => c.close)
          if (closes.length >= 2 && !cancelled) {
            sparksRef.current[item.symbol] = closes.slice(-30)
            setSparkVersion(v => v + 1)
          }
        } catch { /* skip symbols without 5m data */ }
      }
    })()
    return () => { cancelled = true }
  }, [visibleItems, start, end])

  const persist = (next: Record<Exclude<GroupId, 'all'>, WatchItem[]>) => {
    setGroups(next)
    localStorage.setItem(GROUPS_KEY, JSON.stringify(next))
  }

  const addItem = (item: WatchItem) => {
    const target = group === 'all' ? 'intraday' : group
    if (groups[target].some(i => i.symbol === item.symbol)) { toast('info', 'Already in watchlist'); return }
    persist({ ...groups, [target]: [...groups[target], item] })
    subscribe([item.symbol])
    toast('success', `Added ${item.name}`)
    setShowAdd(false)
    setAddSearch('')
    setFreeText('')
  }

  const addFreeText = () => {
    const sym = freeText.trim().toUpperCase()
    if (!sym) return
    addItem({ symbol: sym.includes(':') ? sym : `NSE:${sym}`, name: sym.split(':').pop() || sym, type: sym.includes('CE') || sym.includes('PE') ? 'option' : 'stock' })
  }

  const toggleFav = (symbol: string) => {
    setFavs(prev => {
      const next = prev.includes(symbol) ? prev.filter(s => s !== symbol) : [...prev, symbol]
      localStorage.setItem(FAVS_KEY, JSON.stringify(next))
      return next
    })
  }

  const addableSymbols = [...ALL_SYMBOLS, ...allItems.filter(i => i.type === 'option')]
    .filter(s => !groups[(group === 'all' ? 'intraday' : group) as Exclude<GroupId, 'all'>].some(c => c.symbol === s.symbol))
    .filter(s => s.name.toLowerCase().includes(addSearch.toLowerCase()) || s.symbol.toLowerCase().includes(addSearch.toLowerCase()))
    .filter((s, i, arr) => arr.findIndex(a => a.symbol === s.symbol) === i)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ padding: '10px 10px 6px' }}>
        <div className="t-tabs" style={{ gap: 2, flexWrap: 'wrap' }}>
          {GROUP_ORDER.map(g => (
            <button
              key={g}
              className={`t-tab ${group === g ? 'active' : ''}`}
              onClick={() => setGroup(g)}
              style={{ fontSize: 10, padding: '5px 8px' }}
            >
              {g === 'all' ? 'All' : g === 'etf' ? 'ETF' : g[0].toUpperCase() + g.slice(1)}
            </button>
          ))}
        </div>
        <input className="t-input" placeholder="Filter…" value={search}
          onChange={e => setSearch(e.target.value)} style={{ marginTop: 8, fontSize: 11, padding: '6px 8px' }} />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }} id="ws-watch-scroll">
        <table className="t-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead style={{ position: 'sticky', top: 0, zIndex: 5, background: 'var(--panel)' }}>
            <tr>
              <th style={{ fontSize: 9 }}>SYM</th><th style={{ fontSize: 9 }}>LTP</th><th style={{ fontSize: 9 }}>%</th>
              <th style={{ fontSize: 9 }}>OI</th><th style={{ fontSize: 9 }}>VOL</th><th style={{ fontSize: 9 }}>TREND</th>
              <th style={{ fontSize: 9 }}>CHART</th><th style={{ fontSize: 9 }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {padTop > 0 && <tr style={{ height: padTop }}><td colSpan={8} /></tr>}
            {visibleItems.slice(start, end).map(item => (
              <WatchRow
                key={item.symbol}
                item={item}
                tick={ticks[item.symbol]}
                active={item.symbol === activeSymbol}
                pinned={favs.includes(item.symbol)}
                spark={sparksRef.current[item.symbol]}
                onSelect={onSelectSymbol}
                onBuy={openQuickOrder}
                onSell={openQuickOrder}
                onAnalyze={onAnalyze}
                onToggleFav={toggleFav}
                onAlert={setAlertItem}
              />
            ))}
            {padBottom > 0 && <tr style={{ height: padBottom }}><td colSpan={8} /></tr>}
            {visibleItems.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: 'center', padding: 20 }}><span className="t-faint" style={{ fontSize: 11 }}>Empty — add symbols</span></td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ padding: 8, borderTop: '1px solid var(--border)', display: 'flex', gap: 6 }}>
        <button className="t-btn t-btn-sm t-btn-ghost" style={{ flex: 1, fontSize: 11 }} onClick={() => setShowAdd(true)}>+ Add</button>
        <button className="t-btn t-btn-sm t-btn-ghost" style={{ flex: 1, fontSize: 11 }} onClick={() => window.location.assign('/marketdata')}>Alerts</button>
      </div>

      {showAdd && (
        <div className="t-modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="t-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 380 }}>
            <h3 className="t-modal-title">Add to {group === 'all' ? 'Intraday' : group}</h3>
            <input className="t-input" placeholder="Search…" value={addSearch} onChange={e => setAddSearch(e.target.value)} autoFocus style={{ marginBottom: 8, fontSize: 12 }} />
            <div style={{ maxHeight: 220, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 8 }}>
              {addableSymbols.slice(0, 25).map(s => (
                <div key={s.symbol} className="t-hover-bg" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
                  onClick={() => addItem(s)}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{s.name}</div>
                    <div className="t-faint" style={{ fontSize: 10 }}>{s.symbol}</div>
                  </div>
                  <span className={`t-badge ${s.type === 'index' ? 't-badge-violet' : s.type === 'option' ? 't-badge-amber' : 't-badge-cyan'}`} style={{ fontSize: 9 }}>{s.type}</span>
                </div>
              ))}
              {addableSymbols.length === 0 && <span className="t-faint" style={{ padding: 8, fontSize: 11 }}>No matches</span>}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <input className="t-input" placeholder="Any symbol e.g. NSE:NIFTY26AUG25000CE" value={freeText} onChange={e => setFreeText(e.target.value)} style={{ flex: 1, fontSize: 11 }} />
              <button className="t-btn t-btn-primary" onClick={addFreeText} style={{ fontSize: 11 }}>Add</button>
            </div>
          </div>
        </div>
      )}

      {alertItem && (
        <AlertModal item={alertItem} onClose={() => setAlertItem(null)} />
      )}
    </div>
  )
}

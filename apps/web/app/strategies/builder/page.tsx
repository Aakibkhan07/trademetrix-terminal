'use client'

import { useState, useRef, useCallback } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'

type BlockCategory = 'entry' | 'exit' | 'filter' | 'risk' | 'execution'

interface BlockDef {
  id: string
  name: string
  category: BlockCategory
  color: string
  params: { key: string; label: string; type: 'number' | 'select' | 'text'; default: string; options?: string[] }[]
}

interface PlacedBlock {
  instanceId: string
  blockId: string
  x: number
  y: number
  config: Record<string, string>
}

const BLOCK_PALETTE: BlockDef[] = [
  // Entry Signals
  { id: 'ema_cross', name: 'EMA Crossover', category: 'entry', color: '#00d4ff', params: [
    { key: 'fast_period', label: 'Fast Period', type: 'number', default: '9' },
    { key: 'slow_period', label: 'Slow Period', type: 'number', default: '21' },
    { key: 'direction', label: 'Direction', type: 'select', default: 'above', options: ['above', 'below'] },
  ]},
  { id: 'rsi_oversold', name: 'RSI Oversold', category: 'entry', color: '#00d4ff', params: [
    { key: 'period', label: 'Period', type: 'number', default: '14' },
    { key: 'threshold', label: 'Threshold', type: 'number', default: '30' },
  ]},
  { id: 'price_breakout', name: 'Price Breakout', category: 'entry', color: '#00d4ff', params: [
    { key: 'lookback', label: 'Lookback', type: 'number', default: '20' },
    { key: 'multiplier', label: 'ATR Multiplier', type: 'number', default: '1.5' },
  ]},
  { id: 'volume_spike', name: 'Volume Spike', category: 'entry', color: '#00d4ff', params: [
    { key: 'multiplier', label: 'Avg Multiplier', type: 'number', default: '2' },
  ]},
  { id: 'vwap_touch', name: 'VWAP Touch', category: 'entry', color: '#00d4ff', params: [
    { key: 'deviation', label: 'Deviation %', type: 'number', default: '0.5' },
    { key: 'side', label: 'Side', type: 'select', default: 'above', options: ['above', 'below'] },
  ]},
  { id: 'macd_cross', name: 'MACD Cross', category: 'entry', color: '#00d4ff', params: [
    { key: 'fast', label: 'Fast', type: 'number', default: '12' },
    { key: 'slow', label: 'Slow', type: 'number', default: '26' },
    { key: 'signal', label: 'Signal', type: 'number', default: '9' },
  ]},
  { id: 'bollinger_touch', name: 'Bollinger Touch', category: 'entry', color: '#00d4ff', params: [
    { key: 'period', label: 'Period', type: 'number', default: '20' },
    { key: 'std_dev', label: 'Std Dev', type: 'number', default: '2' },
    { key: 'band', label: 'Band', type: 'select', default: 'upper', options: ['upper', 'lower'] },
  ]},
  { id: 'sup_res_break', name: 'S/R Breakout', category: 'entry', color: '#00d4ff', params: [
    { key: 'lookback', label: 'Lookback', type: 'number', default: '50' },
    { key: 'confirmation', label: 'Confirmation %', type: 'number', default: '0.5' },
  ]},
  { id: 'gap_trade', name: 'Gap Up/Down', category: 'entry', color: '#00d4ff', params: [
    { key: 'min_gap', label: 'Min Gap %', type: 'number', default: '0.5' },
    { key: 'direction', label: 'Direction', type: 'select', default: 'up', options: ['up', 'down'] },
  ]},
  { id: 'news_sentiment', name: 'News Sentiment', category: 'entry', color: '#00d4ff', params: [
    { key: 'min_score', label: 'Min Score', type: 'number', default: '0.7' },
  ]},

  // Exit Signals
  { id: 'trailing_stop', name: 'Trailing Stop', category: 'exit', color: '#7c5cfc', params: [
    { key: 'trail_pct', label: 'Trail %', type: 'number', default: '1' },
    { key: 'activation_pct', label: 'Activation %', type: 'number', default: '0.5' },
  ]},
  { id: 'fixed_target', name: 'Fixed Target', category: 'exit', color: '#7c5cfc', params: [
    { key: 'target_pct', label: 'Target %', type: 'number', default: '2' },
  ]},
  { id: 'time_exit', name: 'Time Exit', category: 'exit', color: '#7c5cfc', params: [
    { key: 'minutes', label: 'Minutes', type: 'number', default: '30' },
  ]},
  { id: 'rsi_exit', name: 'RSI Exit', category: 'exit', color: '#7c5cfc', params: [
    { key: 'period', label: 'Period', type: 'number', default: '14' },
    { key: 'overbought', label: 'Overbought', type: 'number', default: '70' },
    { key: 'oversold', label: 'Oversold', type: 'number', default: '30' },
  ]},
  { id: 'atr_trailing', name: 'ATR Trailing', category: 'exit', color: '#7c5cfc', params: [
    { key: 'atr_period', label: 'ATR Period', type: 'number', default: '14' },
    { key: 'multiplier', label: 'Multiplier', type: 'number', default: '2' },
  ]},

  // Filters
  { id: 'volume_filter', name: 'Volume Filter', category: 'filter', color: '#22c55e', params: [
    { key: 'min_volume', label: 'Min Volume', type: 'number', default: '100000' },
  ]},
  { id: 'time_filter', name: 'Time Filter', category: 'filter', color: '#22c55e', params: [
    { key: 'start_hour', label: 'Start Hour', type: 'number', default: '915' },
    { key: 'end_hour', label: 'End Hour', type: 'number', default: '1500' },
  ]},
  { id: 'day_filter', name: 'Day Filter', category: 'filter', color: '#22c55e', params: [
    { key: 'days', label: 'Trading Days', type: 'select', default: 'all', options: ['all', 'mon-wed', 'thu-fri', 'expiry_only'] },
  ]},
  { id: 'vol_filter', name: 'Volatility Filter', category: 'filter', color: '#22c55e', params: [
    { key: 'min_iv', label: 'Min IV', type: 'number', default: '15' },
    { key: 'max_iv', label: 'Max IV', type: 'number', default: '40' },
  ]},

  // Risk Management
  { id: 'position_sizing', name: 'Position Sizing', category: 'risk', color: '#f59e0b', params: [
    { key: 'method', label: 'Method', type: 'select', default: 'fixed', options: ['fixed', 'percent', 'kelly'] },
    { key: 'value', label: 'Value', type: 'number', default: '1' },
  ]},
  { id: 'max_loss', name: 'Max Loss Limit', category: 'risk', color: '#f59e0b', params: [
    { key: 'max_loss_pct', label: 'Max Loss %', type: 'number', default: '2' },
  ]},
  { id: 'correlation_check', name: 'Correlation Check', category: 'risk', color: '#f59e0b', params: [
    { key: 'max_correlation', label: 'Max Correlation', type: 'number', default: '0.7' },
  ]},
  { id: 'drawdown_limit', name: 'Drawdown Limit', category: 'risk', color: '#f59e0b', params: [
    { key: 'max_dd_pct', label: 'Max DD %', type: 'number', default: '5' },
    { key: 'cooldown_min', label: 'Cooldown Min', type: 'number', default: '60' },
  ]},

  // Execution
  { id: 'market_order', name: 'Market Order', category: 'execution', color: '#3b82f6', params: [
    { key: 'product', label: 'Product', type: 'select', default: 'intraday', options: ['intraday', 'delivery'] },
  ]},
  { id: 'limit_order', name: 'Limit Order', category: 'execution', color: '#3b82f6', params: [
    { key: 'offset_ticks', label: 'Offset Ticks', type: 'number', default: '2' },
    { key: 'product', label: 'Product', type: 'select', default: 'intraday', options: ['intraday', 'delivery'] },
  ]},
  { id: 'slippage_order', name: 'SL-M Order', category: 'execution', color: '#3b82f6', params: [
    { key: 'trigger_offset', label: 'Trigger Offset %', type: 'number', default: '0.3' },
  ]},
  { id: 'bracket_order', name: 'Bracket Order', category: 'execution', color: '#3b82f6', params: [
    { key: 'stop_loss', label: 'Stop Loss %', type: 'number', default: '1' },
    { key: 'take_profit', label: 'Take Profit %', type: 'number', default: '2' },
    { key: 'trailing', label: 'Trailing SL', type: 'select', default: 'no', options: ['yes', 'no'] },
  ]},
]

const BLOCKS_BY_CATEGORY: Record<BlockCategory, { label: string; icon: string }> = {
  entry: { label: 'Entry Signals', icon: '▶' },
  exit: { label: 'Exit Signals', icon: '■' },
  filter: { label: 'Filters', icon: '◈' },
  risk: { label: 'Risk Management', icon: '▲' },
  execution: { label: 'Execution', icon: '⚙' },
}

let instanceCounter = 0

export default function StrategyBuilderPage() {
  const [blocks, setBlocks] = useState<PlacedBlock[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [strategyName, setStrategyName] = useState('My Strategy')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const canvasRef = useRef<HTMLDivElement>(null)

  const selectedBlock = blocks.find(b => b.instanceId === selectedId)
  const selectedDef = selectedBlock ? BLOCK_PALETTE.find(b => b.id === selectedBlock.blockId) : null

  const handleDragStart = useCallback((e: React.DragEvent, blockId: string) => {
    e.dataTransfer.setData('text/plain', blockId)
    e.dataTransfer.effectAllowed = 'copy'
  }, [])

  const handleCanvasDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const blockId = e.dataTransfer.getData('text/plain')
    if (!blockId) return
    const def = BLOCK_PALETTE.find(b => b.id === blockId)
    if (!def) return

    const rect = canvasRef.current?.getBoundingClientRect()
    const x = e.clientX - (rect?.left || 0) - 100
    const y = e.clientY - (rect?.top || 0) - 20

    instanceCounter++
    const newBlock: PlacedBlock = {
      instanceId: `block-${instanceCounter}`,
      blockId,
      x: Math.max(0, x),
      y: Math.max(0, y),
      config: Object.fromEntries(def.params.map(p => [p.key, p.default])),
    }

    setBlocks(prev => [...prev, newBlock])
    setSelectedId(newBlock.instanceId)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }, [])

  const updateBlockConfig = useCallback((instanceId: string, key: string, value: string) => {
    setBlocks(prev => prev.map(b =>
      b.instanceId === instanceId
        ? { ...b, config: { ...b.config, [key]: value } }
        : b
    ))
  }, [])

  const deleteBlock = useCallback((instanceId: string) => {
    setBlocks(prev => prev.filter(b => b.instanceId !== instanceId))
    if (selectedId === instanceId) setSelectedId(null)
  }, [selectedId])

  const handleSave = async () => {
    setSaving(true)
    setSaveError('')
    try {
      const config = {
        blocks: blocks.map(b => ({
          block_id: b.blockId,
          config: b.config,
        })),
      }
      await api.strategies.create({ name: strategyName, type: 'visual', config })
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const getBlockStyle = (block: PlacedBlock) => {
    const def = BLOCK_PALETTE.find(b => b.id === block.blockId)
    return {
      left: block.x,
      top: block.y,
      borderColor: def?.color || 'var(--border)',
      background: `rgba(${def?.color === '#00d4ff' ? '0,212,255' : def?.color === '#7c5cfc' ? '124,92,252' : def?.color === '#22c55e' ? '34,197,94' : def?.color === '#f59e0b' ? '245,158,11' : def?.color === '#3b82f6' ? '59,130,246' : '255,255,255'}, 0.06)`,
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0 }}>
      {/* Top Bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 12px', background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <Link href="/strategies" style={{
          color: 'var(--text-faint)', fontSize: 12, fontWeight: 600, textDecoration: 'none',
        }}>← Strategies</Link>
        <div style={{ width: 1, height: 18, background: 'var(--border)' }} />
        <input
          value={strategyName}
          onChange={e => setStrategyName(e.target.value)}
          style={{
            background: 'none', border: 'none', color: 'var(--text)',
            fontFamily: "'Inter', sans-serif", fontSize: 14, fontWeight: 700,
            outline: 'none', width: 200,
          }}
        />
        <div style={{ flex: 1 }} />
        <button className="t-btn t-btn-sm" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        <Link href="/backtest" className="t-btn t-btn-sm t-btn-primary">
          Backtest
        </Link>
        {saveError && (
          <span style={{ color: 'var(--text-red)', fontSize: 11 }}>{saveError}</span>
        )}
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Left Panel: Block Palette */}
        <div style={{
          width: 200, background: 'var(--bg-secondary)',
          borderRight: '1px solid var(--border)', overflowY: 'auto', flexShrink: 0,
        }}>
          {(Object.entries(BLOCKS_BY_CATEGORY) as [BlockCategory, { label: string; icon: string }][]).map(([cat, meta]) => (
            <div key={cat} style={{ padding: '8px 10px' }}>
              <div style={{
                fontSize: 10, fontWeight: 700, color: 'var(--text-faint)',
                textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6,
              }}>
                {meta.icon} {meta.label}
              </div>
              {BLOCK_PALETTE.filter(b => b.category === cat).map(def => (
                <div
                  key={def.id}
                  draggable
                  onDragStart={e => handleDragStart(e, def.id)}
                  style={{
                    padding: '5px 8px', marginBottom: 3,
                    borderRadius: 'var(--radius-sm)', cursor: 'grab',
                    fontSize: 11, fontWeight: 600, color: 'var(--text-sub)',
                    border: '1px solid transparent',
                    transition: 'all 120ms ease',
                    userSelect: 'none',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--bg-hover)'
                    e.currentTarget.style.color = 'var(--text)'
                    e.currentTarget.style.borderColor = def.color + '40'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'none'
                    e.currentTarget.style.color = 'var(--text-sub)'
                    e.currentTarget.style.borderColor = 'transparent'
                  }}
                >
                  <span style={{ color: def.color, marginRight: 6 }}>◆</span>
                  {def.name}
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Center: Canvas */}
        <div
          ref={canvasRef}
          onDrop={handleCanvasDrop}
          onDragOver={handleDragOver}
          style={{
            flex: 1, position: 'relative', overflow: 'auto',
            background: 'var(--bg)',
            backgroundImage: `
              linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)
            `,
            backgroundSize: '24px 24px',
            minHeight: 0,
          }}
        >
          {blocks.length === 0 && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              pointerEvents: 'none',
            }}>
              <div style={{ textAlign: 'center' }}>
                <p style={{ color: 'var(--text-faint)', fontSize: 13, margin: '0 0 4px' }}>
                  Drag blocks here to build your strategy
                </p>
                <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: 0 }}>
                  Start with an entry signal, add filters, and configure execution
                </p>
              </div>
            </div>
          )}

          {blocks.map(block => {
            const def = BLOCK_PALETTE.find(b => b.id === block.blockId)
            if (!def) return null
            const s = getBlockStyle(block)
            const isSelected = block.instanceId === selectedId

            return (
              <div
                key={block.instanceId}
                onClick={() => setSelectedId(block.instanceId)}
                style={{
                  position: 'absolute', left: block.x, top: block.y,
                  width: 200, cursor: 'pointer',
                  borderRadius: 'var(--radius-md)',
                  border: `1px solid ${isSelected ? def.color : s.borderColor}`,
                  background: s.background,
                  boxShadow: isSelected ? `0 0 12px ${def.color}30` : 'none',
                  transition: 'box-shadow 150ms ease',
                }}
              >
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 10px',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                }}>
                  <span style={{
                    fontSize: 11, fontWeight: 700, color: def.color,
                    fontFamily: "'Inter', sans-serif",
                  }}>
                    {def.name}
                  </span>
                  <button
                    onClick={e => { e.stopPropagation(); deleteBlock(block.instanceId) }}
                    style={{
                      background: 'none', border: 'none', color: 'var(--text-faint)',
                      cursor: 'pointer', fontSize: 12, padding: 0, lineHeight: 1,
                    }}
                  >
                    ✕
                  </button>
                </div>
                <div style={{ padding: '6px 10px', fontSize: 10, color: 'var(--text-faint)' }}>
                  {def.params.slice(0, 2).map(p => (
                    <div key={p.key} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                      <span>{p.label}</span>
                      <span style={{ color: 'var(--text-sub)', fontWeight: 600 }}>{block.config[p.key] || p.default}</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        {/* Right Panel: Configuration */}
        <div style={{
          width: 240, background: 'var(--bg-secondary)',
          borderLeft: '1px solid var(--border)', overflowY: 'auto', flexShrink: 0,
        }}>
          {selectedBlock && selectedDef ? (
            <div style={{ padding: 12 }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
              }}>
                <span style={{ color: selectedDef.color, fontSize: 14 }}>◆</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>
                    {selectedDef.name}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', textTransform: 'capitalize' }}>
                    {selectedDef.category} block
                  </div>
                </div>
              </div>

              {selectedDef.params.map(p => (
                <div key={p.key} style={{ marginBottom: 10 }}>
                  <label style={{
                    display: 'block', fontSize: 10, fontWeight: 700,
                    color: 'var(--text-sub)', marginBottom: 4, textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}>
                    {p.label}
                  </label>
                  {p.type === 'number' ? (
                    <input
                      className="t-input"
                      type="number"
                      value={selectedBlock.config[p.key] || p.default}
                      onChange={e => updateBlockConfig(selectedBlock.instanceId, p.key, e.target.value)}
                      step="any"
                    />
                  ) : p.type === 'select' && p.options ? (
                    <select
                      className="t-select"
                      value={selectedBlock.config[p.key] || p.default}
                      onChange={e => updateBlockConfig(selectedBlock.instanceId, p.key, e.target.value)}
                    >
                      {p.options.map(opt => (
                        <option key={opt} value={opt}>{opt.replace('_', ' ')}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      className="t-input"
                      value={selectedBlock.config[p.key] || p.default}
                      onChange={e => updateBlockConfig(selectedBlock.instanceId, p.key, e.target.value)}
                    />
                  )}
                </div>
              ))}

              <button
                className="t-btn t-btn-sm t-btn-danger"
                onClick={() => deleteBlock(selectedBlock.instanceId)}
                style={{ width: '100%', marginTop: 8 }}
              >
                Remove Block
              </button>
            </div>
          ) : (
            <div style={{ padding: 16, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: '24px 0' }}>
                Select a block on the canvas to configure it
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

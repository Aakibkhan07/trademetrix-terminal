'use client'

import { CSSProperties, useRef } from 'react'
import { BlockMeta, CATEGORY_META, DSLNode, ParamDef, PortDef } from './types'

interface Props {
  node: DSLNode
  meta?: BlockMeta
  selected: boolean
  onDrag: (id: string, dx: number, dy: number) => void
  onDelete: (id: string) => void
  onParamChange: (id: string, key: string, value: unknown) => void
  onPortClick: (nodeId: string, port: PortDef, dir: 'in' | 'out', clientX: number, clientY: number) => void
}

function ParamInput({ def, value, onChange }: { def: ParamDef; value: unknown; onChange: (v: unknown) => void }) {
  const t = def.type
  if (t === 'boolean') {
    return (
      <select
        value={value === true ? 'true' : value === false ? 'false' : ''}
        onChange={e => onChange(e.target.value === 'true')}
        className="t-select"
        style={{ width: '100%', fontSize: 10, padding: '2px 4px' }}
      >
        <option value="">—</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    )
  }
  if (Array.isArray(def.options) && def.options.length) {
    return (
      <select
        value={String(value ?? def.default ?? '')}
        onChange={e => onChange(e.target.value)}
        className="t-select"
        style={{ width: '100%', fontSize: 10, padding: '2px 4px' }}
      >
        <option value="">—</option>
        {def.options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    )
  }
  if (t === 'number') {
    return (
      <input
        type="number"
        value={value === undefined || value === null || value === '' ? '' : String(value)}
        min={def.min ?? undefined}
        max={def.max ?? undefined}
        step={def.step ?? 'any'}
        onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))}
        style={{ width: '100%', fontSize: 10, padding: '2px 4px', background: 'var(--bg-input, #0d1117)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', outline: 'none' }}
      />
    )
  }
  return (
    <input
      type="text"
      value={value === undefined || value === null ? '' : String(value)}
      onChange={e => onChange(e.target.value)}
      style={{ width: '100%', fontSize: 10, padding: '2px 4px', background: 'var(--bg-input, #0d1117)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', outline: 'none' }}
    />
  )
}

function Port({ port, dir }: { port: PortDef; dir: 'in' | 'out' }) {
  return (
    <div
      data-port={`${dir}:${port.name}`}
      className="sb-port"
      style={{
        display: 'flex', alignItems: 'center', gap: 4, padding: '2px 0', cursor: 'crosshair',
        flexDirection: dir === 'out' ? 'row-reverse' : 'row',
      }}
    >
      <span
        className="sb-port-dot"
        style={{
          width: 8, height: 8, borderRadius: 4, display: 'inline-block',
          background: dir === 'out' ? 'var(--text-sub)' : (port.required === false ? 'transparent' : 'var(--text-sub)'),
          border: '1px solid var(--text-sub)', boxSizing: 'border-box', flexShrink: 0,
        }}
      />
      <span className="t-faint" style={{ fontSize: 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {port.label || port.name}
      </span>
    </div>
  )
}

export default function CanvasNode({ node, meta, selected, onDrag, onDelete, onParamChange, onPortClick }: Props) {
  const headerRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ px: number; py: number } | null>(null)
  const color = CATEGORY_META[meta?.category || '']?.color || '#888'

  const startDrag = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('button, select, input, .sb-port')) return
    dragRef.current = { px: e.clientX, py: e.clientY }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }
  const moveDrag = (e: React.PointerEvent) => {
    if (!dragRef.current) return
    onDrag(node.id, e.clientX - dragRef.current.px, e.clientY - dragRef.current.py)
    dragRef.current = { px: e.clientX, py: e.clientY }
  }
  const endDrag = () => { dragRef.current = null }

  const inputs = meta?.inputs || []
  const outputs = meta?.outputs || []

  return (
    <div
      data-node={node.id}
      style={{
        position: 'absolute', width: 212, left: node.position?.x || 0, top: node.position?.y || 0,
        borderRadius: 'var(--radius-md)', border: `1px solid ${selected ? color : 'var(--border)'}`,
        background: 'var(--panel)', boxShadow: selected ? `0 0 0 1px ${color}22, 0 6px 18px rgba(0,0,0,.35)` : '0 4px 14px rgba(0,0,0,.25)',
        overflow: 'hidden', zIndex: selected ? 20 : 10, userSelect: 'none',
      }}
    >
      <div
        ref={headerRef}
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px', cursor: 'grab',
          borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)',
        }}
      >
        <span style={{ width: 6, height: 6, borderRadius: 3, background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--text)', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {meta?.display_name || meta?.name || node.block_type}
        </span>
        <button
          onClick={() => onDelete(node.id)}
          title="Delete node"
          style={{ background: 'none', border: 'none', color: 'var(--text-faint)', fontSize: 12, cursor: 'pointer', padding: '0 2px', lineHeight: 1 }}
        >✕</button>
      </div>

      <div style={{ padding: '4px 8px', display: 'flex', flexDirection: 'column', gap: 3 }}>
        {inputs.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {inputs.map(p => (
              <div key={p.name} data-port-hit={node.id} onClick={e => onPortClick(node.id, p, 'in', e.clientX, e.clientY)}>
                <Port port={p} dir="in" />
              </div>
            ))}
          </div>
        )}
        {(meta?.params || []).length > 0 && (
          <div style={{ borderTop: '1px dashed var(--border)', paddingTop: 4, display: 'flex', flexDirection: 'column', gap: 3 }}>
            {(meta?.params || []).map(p => (
              <label key={p.name} style={{ display: 'block' }}>
                <span className="t-faint" style={{ fontSize: 8, textTransform: 'uppercase', display: 'block', marginBottom: 1 }}>
                  {p.label || p.name.replace(/_/g, ' ')}
                </span>
                <ParamInput def={p} value={node.params?.[p.name]} onChange={v => onParamChange(node.id, p.name, v)} />
              </label>
            ))}
          </div>
        )}
        {outputs.length > 0 && (
          <div style={{ borderTop: '1px dashed var(--border)', paddingTop: 3, display: 'flex', flexDirection: 'column', gap: 1, alignItems: 'flex-end' }}>
            {outputs.map(p => (
              <div key={p.name} data-port-hit={node.id} onClick={e => onPortClick(node.id, p, 'out', e.clientX, e.clientY)}>
                <Port port={p} dir="out" />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

'use client'

import { useMemo, useState } from 'react'
import { BlockMeta, CATEGORY_META } from './types'

interface Props {
  blocks: Record<string, BlockMeta>
  onAdd: (blockType: string, x: number, y: number) => void
  onAddAtCenter: (blockType: string) => void
}

export default function BlockPalette({ blocks, onAdd, onAddAtCenter }: Props) {
  const [cat, setCat] = useState<string>('')
  const [q, setQ] = useState('')

  const list = useMemo(() => {
    const all = Object.values(blocks)
    const groups: { category: string; items: BlockMeta[] }[] = []
    const cats = new Set(all.map(b => b.category))
    for (const c of [...cats].sort()) {
      const items = all.filter(b =>
        b.category === c &&
        (!q || `${b.name} ${b.display_name || ''} ${b.description || ''}`.toLowerCase().includes(q.toLowerCase()))
      )
      if (items.length) groups.push({ category: c, items })
    }
    return groups
  }, [blocks, q])

  const shown = cat ? list.filter(g => g.category === cat) : list

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ padding: '8px 10px 6px', borderBottom: '1px solid var(--border)' }}>
        <span className="t-stat-label" style={{ fontSize: 10, fontWeight: 700 }}>BLOCK PALETTE</span>
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search blocks…"
          style={{
            marginTop: 6, width: '100%', padding: '4px 8px', fontSize: 11, borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)', background: 'var(--bg-input, #0d1117)', color: 'var(--text)',
            outline: 'none',
          }}
        />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
          <button
            className={`t-seg-btn ${!cat ? 'active' : ''}`}
            style={{ fontSize: 9, padding: '1px 6px' }}
            onClick={() => setCat('')}
          >All</button>
          {[...new Set(Object.values(blocks).map(b => b.category))].sort().map(c => (
            <button
              key={c}
              className={`t-seg-btn ${cat === c ? 'active' : ''}`}
              style={{ fontSize: 9, padding: '1px 6px' }}
              onClick={() => setCat(cat === c ? '' : c)}
            >
              {CATEGORY_META[c]?.label || c}
            </button>
          ))}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {shown.length === 0 && <span className="t-faint" style={{ fontSize: 10, padding: 4 }}>No blocks match</span>}
        {shown.map(g => (
          <div key={g.category}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: 3, background: CATEGORY_META[g.category]?.color || '#888' }} />
              <span className="t-faint" style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                {CATEGORY_META[g.category]?.label || g.category}
              </span>
              <span className="t-faint" style={{ fontSize: 9 }}>{g.items.length}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              {g.items.map(b => (
                <div
                  key={b.type}
                  draggable
                  onDragStart={e => {
                    e.dataTransfer.setData('text/block-type', b.type)
                    e.dataTransfer.effectAllowed = 'copy'
                  }}
                  onDoubleClick={() => onAddAtCenter(b.type)}
                  style={{
                    padding: '5px 8px', borderRadius: 'var(--radius-sm)', cursor: 'grab',
                    border: '1px solid var(--border)', background: 'var(--panel)',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <span style={{ width: 5, height: 5, borderRadius: 3, background: CATEGORY_META[b.category]?.color || '#888', flexShrink: 0 }} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {b.display_name || b.name}
                    </div>
                    <div className="t-faint" style={{ fontSize: 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {b.description || b.type}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

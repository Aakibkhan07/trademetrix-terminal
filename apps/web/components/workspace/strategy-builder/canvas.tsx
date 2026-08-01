'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import CanvasNode from './canvas-node'
import { BlockMeta, DSLNode, DSLEdge, PortDef } from './types'

interface Props {
  nodes: DSLNode[]
  edges: DSLEdge[]
  blocks: Record<string, BlockMeta>
  selectedId: string | null
  onSelect: (id: string | null) => void
  onNodesChange: (nodes: DSLNode[]) => void
  onEdgesChange: (edges: DSLEdge[]) => void
  onAddNode: (blockType: string, x: number, y: number) => void
  onAddNodeCentered: (blockType: string) => void
}

type PortKey = string
type Pending = { nodeId: string; portName: string; from: { x: number; y: number } } | null

let edgeSeq = 0
function newEdgeId() {
  edgeSeq += 1
  return `e${Date.now().toString(36)}${edgeSeq}`
}

function edgePath(a: { x: number; y: number }, b: { x: number; y: number }) {
  const dx = Math.max(30, Math.min(90, Math.abs(b.x - a.x) / 2))
  return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`
}

export default function Canvas({ nodes, edges, blocks, selectedId, onSelect, onNodesChange, onEdgesChange, onAddNode, onAddNodeCentered }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [pending, setPending] = useState<Pending>(null)
  const [mouse, setMouse] = useState<{ x: number; y: number } | null>(null)
  const [portPos, setPortPos] = useState<Record<PortKey, { x: number; y: number }>>({})

  const paramsKey = nodes.map(n => JSON.stringify(n.params)).join('|')

  useLayoutEffect(() => {
    const wrap = wrapRef.current
    if (!wrap) return
    const r = wrap.getBoundingClientRect()
    const map: Record<PortKey, { x: number; y: number }> = {}
    wrap.querySelectorAll<HTMLElement>('[data-port]').forEach(el => {
      const key = `${el.closest('[data-node]')?.getAttribute('data-node')}:${el.getAttribute('data-port')}`
      if (!key) return
      const er = el.getBoundingClientRect()
      map[key] = { x: er.left - r.left + er.width / 2, y: er.top - r.top + er.height / 2 }
    })
    setPortPos(map)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, selectedId, paramsKey])

  const toCanvas = useCallback((clientX: number, clientY: number) => {
    const wrap = wrapRef.current
    if (!wrap) return { x: 0, y: 0 }
    const r = wrap.getBoundingClientRect()
    return { x: clientX - r.left, y: clientY - r.top }
  }, [])

  useEffect(() => {
    if (!pending) return
    const fn = (e: MouseEvent) => setMouse(toCanvas(e.clientX, e.clientY))
    window.addEventListener('mousemove', fn)
    return () => window.removeEventListener('mousemove', fn)
  }, [pending, toCanvas])

  const handlePortClick = useCallback((nodeId: string, port: PortDef, dir: 'in' | 'out', clientX: number, clientY: number) => {
    const pt = toCanvas(clientX, clientY)
    if (dir === 'out') {
      setPending({ nodeId, portName: port.name, from: pt })
      setMouse(pt)
      return
    }
    if (pending && pending.nodeId !== nodeId) {
      const dup = edges.some(e =>
        e.source_node === pending.nodeId && e.source_port === pending.portName &&
        e.target_node === nodeId && e.target_port === port.name)
      if (!dup && pending.nodeId !== nodeId) {
        onEdgesChange([...edges, { id: newEdgeId(), source_node: pending.nodeId, source_port: pending.portName, target_node: nodeId, target_port: port.name }])
      }
    }
    setPending(null)
    setMouse(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, edges, toCanvas, onEdgesChange])

  const clearPending = useCallback(() => {
    setPending(null)
    setMouse(null)
    setPortPos({})
  }, [])

  const deleteEdge = useCallback((id: string) => {
    onEdgesChange(edges.filter(e => e.id !== id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edges, onEdgesChange])

  const deleteNode = useCallback((id: string) => {
    onNodesChange(nodes.filter(n => n.id !== id))
    onEdgesChange(edges.filter(e => e.source_node !== id && e.target_node !== id))
    if (selectedId === id) onSelect(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, selectedId, onSelect, onNodesChange, onEdgesChange])

  const dragNode = useCallback((id: string, dx: number, dy: number) => {
    onNodesChange(nodes.map(n => n.id === id ? { ...n, position: { x: (n.position?.x || 0) + dx, y: (n.position?.y || 0) + dy } } : n))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, onNodesChange])

  const setParam = useCallback((id: string, key: string, value: unknown) => {
    onNodesChange(nodes.map(n => n.id === id ? { ...n, params: { ...(n.params || {}), [key]: value } } : n))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, onNodesChange])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const t = e.dataTransfer.getData('text/block-type')
    if (!t) return
    const pt = toCanvas(e.clientX, e.clientY)
    onAddNode(t, Math.max(0, pt.x - 100), Math.max(0, pt.y - 20))
  }, [toCanvas, onAddNode])

  const edgePairs = edges
    .map(e => ({
      id: e.id,
      from: portPos[`${e.source_node}:out:${e.source_port}`],
      to: portPos[`${e.target_node}:in:${e.target_port}`],
    }))
    .filter(p => p.from && p.to)

  return (
    <div
      ref={wrapRef}
      className="sb-canvas"
      style={{ flex: 1, minHeight: 0, overflow: 'auto', position: 'relative', background: 'var(--bg)',
        backgroundImage: 'radial-gradient(var(--border) 1px, transparent 1px)', backgroundSize: '22px 22px' }}
      onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' }}
      onDrop={onDrop}
      onMouseDown={e => { if ((e.target as HTMLElement).dataset.canvas === 'bg') { onSelect(null); clearPending() } }}
    >
      <div data-canvas="bg" style={{ position: 'relative', width: 1600, height: 1000, background: 'transparent' }}>
        <svg
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', overflow: 'visible' }}
        >
          {edgePairs.map(p => (
            <g key={p.id} style={{ pointerEvents: 'stroke' }} onClick={() => deleteEdge(p.id)}>
              <path d={edgePath(p.from, p.to)} stroke="transparent" strokeWidth={12} fill="none" style={{ pointerEvents: 'stroke', cursor: 'pointer' }} />
              <path d={edgePath(p.from, p.to)} stroke="var(--text-sub)" strokeWidth={1.6} fill="none" opacity={0.75} />
            </g>
          ))}
          {pending && mouse && pending.from && (
            <path d={edgePath(pending.from, mouse)} stroke="var(--text-sub)" strokeWidth={1.4} strokeDasharray="4 3" fill="none" />
          )}
        </svg>

        {nodes.map(n => (
          <CanvasNode
            key={n.id}
            node={n}
            meta={blocks[n.block_type]}
            selected={selectedId === n.id}
            onDrag={dragNode}
            onDelete={deleteNode}
            onParamChange={setParam}
            onPortClick={handlePortClick}
          />
        ))}

        {nodes.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
            <div style={{ textAlign: 'center', opacity: .55 }}>
              <div style={{ fontSize: 26, marginBottom: 8 }}>🕸️</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>Drag blocks from the palette onto the canvas</div>
              <div className="t-faint" style={{ fontSize: 10, marginTop: 4 }}>or double-click a block to add it · connect output → input ports</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

'use client'

import { useState } from 'react'
import BlockPalette from './block-palette'
import Canvas from './canvas'
import { BlockMeta, DSL, DSLNode } from './types'

interface Props {
  dsl: DSL
  blocks: Record<string, BlockMeta>
  onChange: (next: DSL) => void
}

function newNodeId() {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function defaultsFor(meta?: BlockMeta): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const p of meta?.params || []) {
    if (p.default !== undefined && p.default !== null) out[p.name] = p.default
  }
  return out
}

export default function AdvancedBuilder({ dsl, blocks, onChange }: Props) {
  const [sel, setSel] = useState<string | null>(null)

  const setNodes = (nodes: DSLNode[]) => onChange({ ...dsl, nodes })
  const setEdges = (edges: DSL['edges']) => onChange({ ...dsl, edges })

  const addNode = (blockType: string, x: number, y: number) => {
    const node: DSLNode = {
      id: newNodeId(),
      block_type: blockType,
      params: defaultsFor(blocks[blockType]),
      position: { x, y },
    }
    setNodes([...dsl.nodes, node])
    setSel(node.id)
  }

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <div style={{ width: 236, borderRight: '1px solid var(--border)', background: 'var(--bg-secondary)', display: 'flex', flexDirection: 'column', minHeight: 0, flexShrink: 0 }}>
        <BlockPalette blocks={blocks} onAdd={addNode} onAddAtCenter={(t) => addNode(t, 420 + (dsl.nodes.length % 5) * 36, 220 + (dsl.nodes.length % 4) * 40)} />
      </div>
      <Canvas
        nodes={dsl.nodes}
        edges={dsl.edges}
        blocks={blocks}
        selectedId={sel}
        onSelect={setSel}
        onNodesChange={setNodes}
        onEdgesChange={setEdges}
        onAddNode={addNode}
        onAddNodeCentered={(t) => addNode(t, 420 + (dsl.nodes.length % 5) * 36, 220 + (dsl.nodes.length % 4) * 40)}
      />
    </div>
  )
}

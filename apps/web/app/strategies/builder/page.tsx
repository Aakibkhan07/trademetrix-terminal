'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { Dialog } from '@/components/ui/dialog'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useUIStore } from '@/lib/stores/ui-store'
import { BlockMeta, DSL, DSLSettings, ValidationIssue } from '@/components/workspace/strategy-builder/types'
import { summarizeDsl } from '@/components/workspace/strategy-builder/dsl-summary'
import StrategySettingsBar from '@/components/workspace/strategy-builder/strategy-settings-bar'
import TemplateGallery from '@/components/workspace/strategy-builder/template-gallery'
import BeginnerBuilder from '@/components/workspace/strategy-builder/beginner-builder'
import NLSummaryCard from '@/components/workspace/strategy-builder/nl-summary-card'
import AdvancedBuilder from '@/components/workspace/strategy-builder/advanced-builder'
import DeployWizard from '@/components/workspace/strategy-builder/deploy-wizard'
import VersionsDrawer from '@/components/workspace/strategy-builder/versions-drawer'
import StrategyScore from '@/components/workspace/strategy-builder/strategy-score'
import StrategyLogs from '@/components/workspace/strategy-builder/strategy-logs'

function shortSymbol(sym: string | null | undefined): string {
  if (!sym) return ''
  const bare = sym.replace(/^NSE:/, '').replace(/-INDEX$/, '')
  return bare
}

function statusBadge(status: string | undefined): string {
  switch (status) {
    case 'published': return 't-badge-green'
    case 'paper': return 't-badge-cyan'
    case 'live': return 't-badge-green'
    case 'stopped': return 't-badge-yellow'
    case 'archived': return 't-badge-sub'
    case 'ready': return 't-badge-green'
    case 'validated': return 't-badge-cyan'
    default: return 't-badge-violet'
  }
}

export default function StrategyBuilderPage() {
  return (
    <Suspense fallback={<div style={{ padding: 20 }}><span className="t-faint" style={{ fontSize: 11 }}>Loading builder…</span></div>}>
      <BuilderInner />
    </Suspense>
  )
}

function BuilderInner() {
  const params = useSearchParams()
  const { activeSymbol } = useUIStore()
  const [mode, setMode] = useState<'beginner' | 'advanced'>('beginner')
  const [dsl, setDsl] = useState<DSL | null>(null)
  const [strategyId, setStrategyId] = useState<string | null>(null)
  const [blocks, setBlocks] = useState<Record<string, BlockMeta>>({})
  const [issues, setIssues] = useState<ValidationIssue[]>([])
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [galleryOpen, setGalleryOpen] = useState(false)
  const [touched, setTouched] = useState(false)
  const [deployOpen, setDeployOpen] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [score, setScore] = useState<{ overall: number; grade: string } | null>(null)

  const presetSymbol = shortSymbol(params.get('symbol')) || shortSymbol(activeSymbol)

  useEffect(() => {
    api.builder.blocks()
      .then(d => {
        const list = (d as { blocks?: BlockMeta[] }).blocks || []
        const map: Record<string, BlockMeta> = {}
        list.forEach(b => { map[b.type] = b })
        setBlocks(map)
      })
      .catch(() => {})
  }, [])

  const load = useCallback((id: string) => {
    setBusy('Loading…')
    api.builder.get(id)
      .then(d => {
        const dsl = d as unknown as DSL
        setDsl(dsl)
        setStrategyId(dsl.id || id)
        setMode('advanced')
        setError('')
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load strategy'))
      .finally(() => setBusy(''))
  }, [])

  useEffect(() => {
    if (params.get('id')) load(params.get('id') as string)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.get('id')])

  const summary = useMemo(() => summarizeDsl(dsl, blocks), [dsl, blocks])

  const applyDsl = useCallback((next: DSL) => {
    if (!next.settings?.symbol) next.settings = { ...(next.settings || {}), symbol: presetSymbol || next.settings?.symbol }
    setDsl(next)
    setStrategyId(next.id || null)
    setTouched(true)
  }, [presetSymbol])

  const startTemplate = useCallback((key: string) => {
    setBusy('Creating…')
    api.builder.create({ template: key })
      .then(d => {
        const dsl = d as unknown as DSL
        applyDsl(dsl)
        setMode('advanced')
        setGalleryOpen(false)
        setError('')
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to create — builder access required?'))
      .finally(() => setBusy(''))
  }, [applyDsl])

  const startBlank = useCallback(() => {
    setBusy('Creating…')
    api.builder.create({})
      .then(d => {
        const dsl = d as unknown as DSL
        applyDsl(dsl)
        setMode('advanced')
        setGalleryOpen(false)
        setError('')
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to create — builder access required?'))
      .finally(() => setBusy(''))
  }, [applyDsl])

  const handleAIResult = useCallback((aiDsl: unknown) => {
    setBusy('Importing…')
    api.builder.import(aiDsl as Record<string, unknown>)
      .then(d => { applyDsl(d as unknown as DSL); setError('') })
      .catch(async () => {
        const raw = aiDsl as Partial<DSL>
        try {
          const created = await api.builder.create({ name: raw.name || 'AI Strategy' })
          const base = created as unknown as DSL
          const merged: DSL = {
            ...(raw as DSL),
            id: base.id,
            name: raw.name || base.name,
            description: raw.description || '',
            status: 'draft',
            version_number: 1,
          }
          await api.builder.update(base.id as string, { name: merged.name, description: merged.description, settings: merged.settings, nodes: merged.nodes, edges: merged.edges })
          setDsl(merged)
          setStrategyId(base.id || null)
          setTouched(true)
          setError('')
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to save AI draft')
        }
      })
      .finally(() => setBusy(''))
  }, [applyDsl])

  const saveDraft = useCallback(async () => {
    if (!strategyId || !dsl) return
    setSaving(true)
    setError('')
    try {
      await api.builder.update(strategyId, {
        name: dsl.name,
        description: dsl.description || '',
        settings: dsl.settings,
        tags: dsl.tags || [],
        nodes: dsl.nodes,
        edges: dsl.edges,
      })
      setTouched(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }, [strategyId, dsl])

  const validateNow = useCallback(async () => {
    if (!strategyId) { setError('Save the draft first.'); return }
    setBusy('Validating…')
    try {
      const res = await api.builder.validate(strategyId)
      setIssues((res as { issues?: ValidationIssue[] })?.issues || [])
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Validation failed')
    } finally {
      setBusy('')
    }
  }, [strategyId])

  const patchSettings = useCallback((patch: Partial<DSLSettings>) => {
    setDsl(prev => prev ? { ...prev, settings: { ...(prev.settings || {}), ...patch } } : prev)
    setTouched(true)
  }, [])

  const patchGraph = useCallback((next: DSL) => {
    setDsl(prev => ({
      ...next,
      id: prev?.id || next.id,
      name: prev?.name || next.name,
      status: prev?.status || next.status,
    }))
    setTouched(true)
  }, [])

  const patchName = useCallback((name: string) => {
    setDsl(prev => prev ? { ...prev, name } : prev)
    setTouched(true)
  }, [])

  const markReady = useCallback(async () => {
    if (!strategyId) { setError('Save the draft first.'); return }
    setBusy('Marking ready…')
    try {
      const res = await api.builder.ready(strategyId)
      setDsl(prev => prev ? { ...prev, status: (res as { status?: string }).status || 'ready' } : prev)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to mark ready')
    } finally {
      setBusy('')
    }
  }, [strategyId])

  const canDeploy = !!strategyId && !!dsl && (dsl.status === 'ready' || dsl.status === 'published' || dsl.status === 'validated' || dsl.status === 'paper' || dsl.status === 'live' || dsl.status === 'stopped')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 12px', background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)', flexShrink: 0, flexWrap: 'wrap',
      }}>
        <Link href="/strategies" style={{ color: 'var(--text-faint)', fontSize: 12, fontWeight: 600, textDecoration: 'none' }}>← Strategies</Link>
        <div style={{ width: 1, height: 18, background: 'var(--border)' }} />
        <input
          value={dsl?.name || ''}
          onChange={e => patchName(e.target.value)}
          placeholder="Untitled Strategy"
          style={{ background: 'none', border: 'none', color: 'var(--text)', fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 700, outline: 'none', width: 220 }}
        />
        {dsl?.status && (
          <span className={`t-badge ${statusBadge(dsl.status)}`} style={{ fontSize: 9, textTransform: 'uppercase' }}>
            {dsl.status}
          </span>
        )}
        {score && score.grade && score.grade !== 'F' && (
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--cyan)' }}>Score {score.grade}</span>
        )}
        <div style={{ flex: 1 }} />
        <div className="t-seg" style={{ height: 26 }}>
          <button className={`t-seg-btn ${mode === 'beginner' ? 'active' : ''}`} onClick={() => setMode('beginner')} style={{ fontSize: 10, padding: '0 10px' }}>Beginner</button>
          <button className={`t-seg-btn ${mode === 'advanced' ? 'active' : ''}`} onClick={() => setMode('advanced')} style={{ fontSize: 10, padding: '0 10px' }}>Advanced</button>
        </div>
        <button className="t-btn t-btn-sm" onClick={() => setGalleryOpen(true)} disabled={!!strategyId && !touched}>Templates</button>
        <button className="t-btn t-btn-sm" onClick={() => setVersionsOpen(true)} disabled={!strategyId} title="Version history & compare">🕘 Versions</button>
        {busy && <span className="t-faint" style={{ fontSize: 10 }}>{busy}</span>}
        <button className="t-btn t-btn-sm" onClick={saveDraft} disabled={saving || !strategyId || !dsl}>
          {saving ? 'Saving…' : '💾 Save draft'}
        </button>
        <button className="t-btn t-btn-sm" onClick={validateNow} disabled={!strategyId}>
          ✓ Validate
        </button>
        <button className="t-btn t-btn-sm" onClick={markReady} disabled={!strategyId} title="Mark as ready for deployment">
          ✔ Ready
        </button>
        <button className="t-btn t-btn-sm t-btn-primary" disabled={!canDeploy} onClick={() => setDeployOpen(true)}>
          ▶ Deploy
        </button>
        {error && <span style={{ color: 'var(--text-red)', fontSize: 11, flexBasis: '100%' }}>{error}</span>}
      </div>

      <StrategySettingsBar settings={dsl?.settings || {}} onChange={patchSettings} disabled={!strategyId || !touched} />

      <div style={{ display: 'flex', flex: 1, minHeight: 0, flexDirection: 'column', overflowY: 'auto' }}>
        {mode === 'beginner' ? (
          <BeginnerBuilder onResult={handleAIResult} onError={setError} />
        ) : !dsl ? (
          <div style={{ padding: 14, maxWidth: 720 }}>
            <TemplateGallery onUse={startTemplate} onBlank={startBlank} onAI={() => setMode('beginner')} />
          </div>
        ) : (
          <AdvancedBuilder dsl={dsl} blocks={blocks} onChange={patchGraph} />
        )}
      </div>

      <div style={{ display: 'flex', gap: 12, padding: '0 14px 10px', flexShrink: 0, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 360px', minWidth: 280 }}>
          <NLSummaryCard lines={summary.lines} valid={summary.valid} issues={summary.issues} serverIssues={issues} />
        </div>
        {strategyId && (
          <>
            <div className="t-panel" style={{ padding: '10px 12px', flex: '0 1 300px', minWidth: 240 }}>
              <p style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 700 }}>Validation Score</p>
              <StrategyScore strategyId={strategyId} onScore={s => setScore(s)} />
            </div>
            <div className="t-panel" style={{ padding: '10px 12px', flex: '1 1 400px', minWidth: 280 }}>
              <p style={{ margin: '0 0 8px', fontSize: 11, fontWeight: 700 }}>Strategy Logs</p>
              <StrategyLogs strategyId={strategyId} />
            </div>
          </>
        )}
      </div>

      {galleryOpen && (
        <Dialog onClose={() => setGalleryOpen(false)} maxWidth={620} padding={0} title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>New Strategy</span>
            <button className="t-btn t-btn-sm" onClick={() => setGalleryOpen(false)}>✕</button>
          </div>
        }>
            <TemplateGallery onUse={startTemplate} onBlank={startBlank} onAI={() => { setGalleryOpen(false); setMode('beginner') }} />
        </Dialog>
      )}

      {deployOpen && strategyId && (
        <DeployWizard
          strategyId={strategyId}
          status={dsl?.status || 'draft'}
          defaultSymbol={dsl?.settings?.symbol}
          onClose={() => setDeployOpen(false)}
          onDeployed={() => {
            setDeployOpen(false)
            setError('')
            const status = (dsl?.settings?.symbol === 'live') ? 'live' : 'paper'
            setDsl(prev => prev ? { ...prev, status } : prev)
            setTouched(false)
          }}
        />
      )}

      {versionsOpen && strategyId && (
        <VersionsDrawer
          strategyId={strategyId}
          onClose={() => setVersionsOpen(false)}
          onRestored={() => {
            api.builder.get(strategyId)
              .then(d => { const dsl = d as unknown as DSL; setDsl(dsl); setTouched(true) })
              .catch(() => {})
          }}
        />
      )}
    </div>
  )
}

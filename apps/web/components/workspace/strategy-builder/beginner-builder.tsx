'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

interface Props {
  onResult: (dsl: unknown) => void
  onError: (msg: string) => void
}

const EXAMPLES = [
  'EMA crossover on NIFTY 5m: buy when EMA 9 crosses above EMA 21, exit when it crosses below. Target +1%, SL 0.5%.',
  'Buy BANKNIFTY when price breaks above the first 15-minute high with volume confirmation, SL at the low of the range.',
  'RSI mean reversion: buy NIFTY when RSI 14 drops below 30 and crosses back above, exit at RSI 60.',
]

export default function BeginnerBuilder({ onResult, onError }: Props) {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const generate = async () => {
    if (!prompt.trim() || busy) return
    setBusy(true)
    setErr('')
    try {
      const d = await api.ai.buildStrategy(prompt.trim())
      const strategy = (d as { strategy?: unknown }).strategy
      if (!strategy) throw new Error('AI returned an empty draft')
      onResult(strategy)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Generation failed'
      setErr(msg)
      onError(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 14, maxWidth: 720 }}>
      <div>
        <div className="t-stat-label" style={{ fontSize: 10, fontWeight: 700, marginBottom: 6 }}>
          DESCRIBE YOUR STRATEGY IN PLAIN ENGLISH
        </div>
        <textarea
          className="t-input"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="e.g. Buy NIFTY when EMA 9 crosses above EMA 21, exit at +1% target with 0.5% SL, only 09:30–14:30 on weekdays"
          style={{ width: '100%', minHeight: 84, fontSize: 12, resize: 'vertical', fontFamily: 'var(--font-body)' }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          <button className="t-btn t-btn-primary t-btn-sm" onClick={generate} disabled={busy || !prompt.trim()}>
            {busy ? 'Generating…' : '✨ Generate strategy'}
          </button>
          {err && <span style={{ color: 'var(--text-red)', fontSize: 11 }}>{err}</span>}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span className="t-faint" style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Try an example
        </span>
        {EXAMPLES.map((ex, i) => (
          <button
            key={i}
            className="t-btn t-btn-ghost"
            style={{ textAlign: 'left', fontSize: 10, padding: '5px 8px', height: 'auto', lineHeight: 1.4, color: 'var(--text-sub)' }}
            onClick={() => setPrompt(ex)}
          >
            {ex}
          </button>
        ))}
      </div>
      <p className="t-faint" style={{ fontSize: 10, margin: 0 }}>
        The AI draft is a starting point — you can review, fix and publish it in Advanced mode. Everything passes the same validation as hand-built strategies.
      </p>
    </div>
  )
}

'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export default function AIPage() {
  const [command, setCommand] = useState('')
  const [response, setResponse] = useState('')
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null)
  const [analysing, setAnalysing] = useState(false)

  const handleCommand = async () => {
    if (!command.trim()) return
    setLoading(true)
    setResponse('')
    try {
      const result = await api.ai.desk(command)
      setResponse((result as { response: string }).response || 'No response')
    } catch (err: unknown) {
      setResponse(err instanceof Error ? err.message : 'Command failed')
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyse = async () => {
    setAnalysing(true)
    try {
      const result = await api.ai.journal(7)
      setAnalysis((result as { analysis: Record<string, unknown> }).analysis || null)
    } catch {
      setAnalysis({ summary: 'Could not load analysis' })
    } finally {
      setAnalysing(false)
    }
  }

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <h1 className="page-title">AI Trading Desk</h1>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Command Desk</h3>
          </div>
          <p style={{ color: '#8888a0', fontSize: 13, marginBottom: 12 }}>
            Ask questions about your account or give commands in plain language.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="input"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="e.g. How did my strategies perform today?"
              onKeyDown={(e) => e.key === 'Enter' && handleCommand()}
            />
            <button className="btn btn-cyan" onClick={handleCommand} disabled={loading}>
              {loading ? '...' : 'Send'}
            </button>
          </div>
          {response && (
            <div style={{ marginTop: 16, padding: 12, background: '#15152a', borderRadius: 8 }}>
              <p style={{ margin: 0, fontSize: 14, whiteSpace: 'pre-wrap' }}>{response}</p>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">AI Trade Journal</h3>
          </div>
          <p style={{ color: '#8888a0', fontSize: 13, marginBottom: 12 }}>
            Get psychological and statistical feedback on your trading behaviour.
          </p>
          <button className="btn btn-primary" onClick={handleAnalyse} disabled={analysing}>
            {analysing ? 'Analysing...' : 'Analyse Last 7 Days'}
          </button>
          {analysis && (
            <div style={{ marginTop: 16 }}>
              <div style={{ padding: 12, background: '#15152a', borderRadius: 8 }}>
                <p style={{ margin: 0, fontSize: 14, whiteSpace: 'pre-wrap' }}>
                  {(analysis as Record<string, unknown>).summary as string || JSON.stringify(analysis, null, 2)}
                </p>
              </div>
               {analysis && typeof (analysis as Record<string, unknown>).score === 'number' && (
                <div style={{ marginTop: 12, textAlign: 'center' }}>
                  <p style={{ color: '#8888a0', fontSize: 12, marginBottom: 4 }}>Discipline Score</p>
                  <p className="numeric neon-violet" style={{ fontSize: 36, fontWeight: 700, margin: 0 }}>
                    {(analysis as Record<string, number>).score}/100
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

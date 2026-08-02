'use client'

import { useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/lib/use-toast'
import { SkeletonGrid } from '@/components/skeleton'
import { ErrorMessage } from '@/components/error-message'

interface FeedbackItem {
  id: number
  category: string
  title: string
  description: string
  status: string
  notes?: string | null
  created_at?: string
}

const CATEGORY_LABEL: Record<string, string> = {
  bug: 'Bug Report',
  feature: 'Feature Request',
  nps: 'NPS Survey',
  report: 'Report',
}

const STATUS_COLOR: Record<string, string> = {
  new: 'var(--violet)',
  triaged: 'var(--amber)',
  resolved: 'var(--green)',
  wontfix: 'var(--text-faint)',
}

export default function FeedbackPage() {
  const { toast } = useToast()
  const [activeTab, setActiveTab] = useState<'bug' | 'feature' | 'nps'>('bug')
  const [form, setForm] = useState({ title: '', description: '', email: '' })
  const [npsScore, setNpsScore] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [history, setHistory] = useState<FeedbackItem[] | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const loadHistory = useCallback(async () => {
    try {
      const res = await api.feedback.myHistory()
      setHistory(res.feedback)
      setHistoryError(null)
    } catch {
      setHistoryError('Could not load your submission history')
    }
  }, [])

  const refreshAfterSubmit = useCallback(() => {
    setTimeout(() => { void loadHistory() }, 400)
  }, [loadHistory])

  const handleSubmit = async () => {
    if (activeTab === 'nps' && npsScore === null) return
    if (activeTab !== 'nps' && !form.title.trim()) return
    setSubmitting(true)
    try {
      const metadata: Record<string, unknown> = { page: '/feedback' }
      if (activeTab === 'nps') {
        metadata.nps_score = npsScore
      } else if (form.email.trim()) {
        metadata.email = form.email.trim()
      }
      await api.feedback.submit({
        category: activeTab,
        title: activeTab === 'nps' ? `NPS: ${npsScore}/10` : form.title.trim(),
        description: form.description.trim(),
        metadata,
      })
      toast('success', activeTab === 'bug' ? 'Bug report submitted' : activeTab === 'feature' ? 'Feature request submitted' : 'Feedback submitted')
      setForm({ title: '', description: '', email: '' })
      setNpsScore(null)
      if (!history) loadHistory()
      refreshAfterSubmit()
    } catch {
      toast('error', 'Failed to submit feedback. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const hasHistory = history && history.length > 0

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Feedback</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Help us improve TradeMetrix Terminal — your submissions are tracked and reviewed</p>
      </div>

      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(139,92,246,0.15)' }}>
        {(['bug', 'feature', 'nps'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '8px 16px', fontSize: 12, fontWeight: activeTab === tab ? 600 : 400,
            background: 'none', border: 'none', borderBottom: activeTab === tab ? '2px solid var(--violet)' : '2px solid transparent',
            color: activeTab === tab ? 'var(--violet)' : 'var(--text-faint)', cursor: 'pointer', fontFamily: 'inherit',
          }}>{tab === 'bug' ? 'Bug Report' : tab === 'feature' ? 'Feature Request' : 'NPS Survey'}</button>
        ))}
      </div>

      <div className="t-panel" style={{ padding: 20 }}>
        {activeTab === 'nps' ? (
          <div>
            <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600 }}>How likely are you to recommend TradeMetrix?</h3>
            <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginBottom: 20 }}>
              {[0,1,2,3,4,5,6,7,8,9,10].map(n => (
                <button key={n} onClick={() => setNpsScore(n)} style={{
                  width: 36, height: 36, borderRadius: 8, border: '1px solid var(--border)',
                  background: npsScore === n ? 'var(--violet)' : 'var(--panel)',
                  color: npsScore === n ? '#fff' : 'var(--text)', cursor: 'pointer',
                  fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                }}>{n}</button>
              ))}
            </div>
            <div className="t-panel" style={{ padding: 16, marginBottom: 16 }}>
              <label className="t-label" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>Additional comments (optional)</label>
              <textarea className="t-input" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={{ width: '100%', minHeight: 80, fontSize: 12, resize: 'vertical' }} />
            </div>
            <button className="t-btn t-btn-primary t-btn-sm" onClick={handleSubmit} disabled={npsScore === null || submitting} style={{ fontSize: 11 }}>
              {submitting ? 'Submitting...' : 'Submit Feedback'}
            </button>
          </div>
        ) : (
          <div>
            <div style={{ marginBottom: 16 }}>
              <label className="t-label" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>Title</label>
              <input className="t-input" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="Brief description" style={{ width: '100%', fontSize: 12 }} />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label className="t-label" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>Description</label>
              <textarea className="t-input" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Detailed description..." style={{ width: '100%', minHeight: 120, fontSize: 12, resize: 'vertical' }} />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label className="t-label" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>Email (optional)</label>
              <input className="t-input" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="user@example.com" style={{ width: '100%', fontSize: 12 }} />
            </div>
            <button className="t-btn t-btn-primary t-btn-sm" onClick={handleSubmit} disabled={!form.title.trim() || submitting} style={{ fontSize: 11 }}>
              {submitting ? 'Submitting...' : activeTab === 'bug' ? 'Report Bug' : 'Submit Request'}
            </button>
          </div>
        )}
      </div>

      <div style={{ marginTop: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 className="t-page-title" style={{ fontSize: 14, margin: 0 }}>Your Submissions</h2>
          <button className="t-btn t-btn-sm" onClick={() => void loadHistory()} style={{ fontSize: 10 }}>
            {history === null ? 'Load history' : 'Refresh'}
          </button>
        </div>

        {history === null && !historyError && (
          <SkeletonGrid count={2} />
        )}
        {historyError && (
          <ErrorMessage message={historyError} onRetry={() => void loadHistory()} />
        )}
        {hasHistory && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {history.map(item => (
              <div key={item.id} className="t-panel" style={{ padding: '12px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>
                    {item.title || CATEGORY_LABEL[item.category] || item.category}
                  </span>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '2px 8px', borderRadius: 4, fontSize: 9, fontWeight: 600,
                    background: `${STATUS_COLOR[item.status] || 'var(--text-faint)'}20`,
                    color: STATUS_COLOR[item.status] || 'var(--text-faint)',
                  }}>{item.status || 'new'}</span>
                </div>
                {item.description && (
                  <p style={{ margin: '0 0 6px', fontSize: 11, color: 'var(--text-sub)', lineHeight: 1.5 }}>{item.description}</p>
                )}
                <div style={{ display: 'flex', gap: 12, fontSize: 9, color: 'var(--text-faint)' }}>
                  <span>{CATEGORY_LABEL[item.category] || item.category}</span>
                  {item.created_at && <span>{new Date(item.created_at).toLocaleString()}</span>}
                  {item.status === 'resolved' && item.notes && <span>Note: {item.notes}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
        {history && history.length === 0 && (
          <p style={{ color: 'var(--text-faint)', fontSize: 11, margin: 0 }}>No submissions yet — your feedback history will appear here.</p>
        )}
      </div>
    </div>
  )
}

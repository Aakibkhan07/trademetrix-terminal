'use client'

import { useState } from 'react'
import { useToast } from '@/lib/use-toast'

export default function FeedbackPage() {
  const { toast } = useToast()
  const [activeTab, setActiveTab] = useState<'bug' | 'feature' | 'nps'>('bug')
  const [form, setForm] = useState({ title: '', description: '', email: '' })
  const [npsScore, setNpsScore] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    setSubmitting(true)
    await new Promise(r => setTimeout(r, 500))
    toast('success', activeTab === 'bug' ? 'Bug report submitted' : activeTab === 'feature' ? 'Feature request submitted' : 'Feedback submitted')
    setForm({ title: '', description: '', email: '' })
    setNpsScore(null)
    setSubmitting(false)
  }

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Feedback</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Help us improve TradeMetrix Terminal</p>
      </div>

      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(139,92,246,0.15)' }}>
        {(['bug', 'feature', 'nps'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '8px 16px', fontSize: 12, fontWeight: activeTab === tab ? 600 : 400,
            background: 'none', border: 'none', borderBottom: activeTab === tab ? '2px solid var(--violet)' : '2px solid transparent',
            color: activeTab === tab ? 'var(--violet)' : '#8888a0', cursor: 'pointer', fontFamily: 'inherit',
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
    </div>
  )
}

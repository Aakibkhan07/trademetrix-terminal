'use client'

import { useState, useCallback } from 'react'
import { useAuth } from '@/lib/auth-context'
import { useToast } from '@/lib/use-toast'
import { EmptyState } from '@/components/empty-state'

const TABS = ['Invite Codes', 'Waitlist', 'Approvals'] as const
type Tab = (typeof TABS)[number]

type InviteCode = { code: string; status: 'available' | 'used' | 'revoked' }
type WaitlistEntry = { email: string; name: string; date: string; status: 'Pending' | 'Approved' | 'Rejected' }
type ApprovalEntry = { email: string; name: string; code: string }

function generateCode(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  for (let i = 0; i < 8; i++) result += chars.charAt(Math.floor(Math.random() * chars.length))
  return result
}

export default function BetaPage() {
  const { isAdmin, loading: authLoading } = useAuth()
  if (authLoading) {
    return (
      <div>
        <div style={{ marginBottom: 24 }}><h1 className="t-page-title">Beta Program Management</h1></div>
        <div className="t-panel" style={{ padding: 20 }}>
          <div style={{ height: 12, width: '50%', background: 'rgba(139,92,246,0.08)', borderRadius: 4, marginBottom: 8 }} />
          <div style={{ height: 12, width: '70%', background: 'rgba(139,92,246,0.08)', borderRadius: 4 }} />
        </div>
      </div>
    )
  }
  if (!isAdmin) {
    return (
      <div>
        <div style={{ marginBottom: 24 }}>
          <h1 className="t-page-title">Beta Program Management</h1>
          <p className="t-sub" style={{ fontSize: 13 }}>Invite codes, waitlist, and approvals</p>
        </div>
        <div style={{ padding: '12px 16px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, color: '#ef4444', fontSize: 13 }}>
          You do not have admin access.
        </div>
      </div>
    )
  }
  return <BetaManagement />
}

function BetaManagement() {
  const [activeTab, setActiveTab] = useState<Tab>('Invite Codes')
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 className="t-page-title">Beta Program Management</h1>
        <p className="t-sub" style={{ fontSize: 13 }}>Invite codes, waitlist, and approvals</p>
      </div>
      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(139,92,246,0.15)' }}>
        {TABS.map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '8px 16px', fontSize: 12, fontWeight: activeTab === tab ? 600 : 400,
            background: 'none', border: 'none', borderBottom: activeTab === tab ? '2px solid var(--violet)' : '2px solid transparent',
            color: activeTab === tab ? 'var(--violet)' : '#8888a0', cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'inherit',
          }}>{tab}</button>
        ))}
      </div>
      {activeTab === 'Invite Codes' && <InviteCodesSection />}
      {activeTab === 'Waitlist' && <WaitlistSection />}
      {activeTab === 'Approvals' && <ApprovalsSection />}
    </div>
  )
}

function InviteCodesSection() {
  const { toast } = useToast()
  const [count, setCount] = useState(1)
  const [codes, setCodes] = useState<InviteCode[]>([])

  const handleGenerate = useCallback(() => {
    const generated: InviteCode[] = Array.from({ length: count }, () => ({ code: generateCode(), status: 'available' }))
    setCodes(prev => [...prev, ...generated])
    toast('success', `Generated ${count} invite code(s)`)
  }, [count, toast])

  const handleCopy = useCallback(async (code: string) => {
    try { await navigator.clipboard.writeText(code); toast('success', 'Code copied to clipboard') }
    catch { toast('error', 'Failed to copy') }
  }, [toast])

  const handleRevoke = useCallback((code: string) => {
    setCodes(prev => prev.map(c => c.code === code ? { ...c, status: 'revoked' as const } : c))
    toast('info', 'Code revoked')
  }, [toast])

  return (
    <div>
      <div className="t-panel" style={{ padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Number of codes to generate</label>
            <input className="t-input" type="number" min={1} max={100} value={count}
              onChange={e => setCount(Math.max(1, parseInt(e.target.value) || 1))} style={{ width: 120, fontSize: 12 }} />
          </div>
          <button className="t-btn t-btn-primary t-btn-sm" onClick={handleGenerate} style={{ fontSize: 11 }}>Generate Codes</button>
        </div>
      </div>
      {codes.length === 0 ? (
        <EmptyState icon="#" title="No invite codes generated" description="Use the form above to generate new beta invite codes." />
      ) : (
        <div className="t-panel" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(139,92,246,0.12)' }}>
                <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>CODE</th>
                <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>STATUS</th>
                <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {codes.map(c => (
                <tr key={c.code} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.05em', userSelect: 'all' }}>{c.code}</td>
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      padding: '2px 8px', borderRadius: 4, fontSize: 9, fontWeight: 600,
                      background: c.status === 'available' ? 'rgba(34,197,94,0.15)' : c.status === 'used' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
                      color: c.status === 'available' ? '#22c55e' : c.status === 'used' ? '#f59e0b' : '#ef4444',
                    }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: c.status === 'available' ? '#22c55e' : c.status === 'used' ? '#f59e0b' : '#ef4444', display: 'inline-block', marginRight: 4 }} />
                      {c.status.charAt(0).toUpperCase() + c.status.slice(1)}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                      <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => handleCopy(c.code)} style={{ fontSize: 9 }}>Copy</button>
                      {c.status !== 'revoked' && (
                        <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => handleRevoke(c.code)} style={{ fontSize: 9, color: '#ef4444' }}>Revoke</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function WaitlistSection() {
  const { toast } = useToast()
  const [entries, setEntries] = useState<WaitlistEntry[]>([
    { email: 'user1@example.com', name: 'John Doe', date: '2026-07-01', status: 'Pending' },
    { email: 'user2@example.com', name: 'Jane Smith', date: '2026-07-02', status: 'Approved' },
    { email: 'user3@example.com', name: 'Bob Wilson', date: '2026-07-03', status: 'Pending' },
  ])
  const [newEmail, setNewEmail] = useState('')
  const [newName, setNewName] = useState('')

  const handleAdd = useCallback(() => {
    if (!newEmail.trim() || !newName.trim()) { toast('error', 'Email and name are required'); return }
    setEntries(prev => [...prev, { email: newEmail.trim(), name: newName.trim(), date: new Date().toISOString().slice(0, 10), status: 'Pending' }])
    setNewEmail(''); setNewName(''); toast('success', `${newName} added to waitlist`)
  }, [newEmail, newName, toast])

  const handleApprove = useCallback((email: string) => {
    setEntries(prev => prev.map(e => e.email === email ? { ...e, status: 'Approved' as const } : e))
    toast('success', `${email} approved`)
  }, [toast])

  const handleReject = useCallback((email: string) => {
    setEntries(prev => prev.map(e => e.email === email ? { ...e, status: 'Rejected' as const } : e))
    toast('info', `${email} rejected`)
  }, [toast])

  return (
    <div>
      <div className="t-panel" style={{ padding: 16, marginBottom: 16 }}>
        <h3 style={{ fontFamily: 'Outfit', fontSize: 13, margin: '0 0 10px', color: '#f0f0f5' }}>Add to Waitlist</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Email</label>
            <input className="t-input" type="email" value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="user@example.com" style={{ width: 220, fontSize: 12 }} />
          </div>
          <div>
            <label className="t-label" style={{ fontSize: 10, marginBottom: 4, display: 'block' }}>Name</label>
            <input className="t-input" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Full name" style={{ width: 200, fontSize: 12 }} />
          </div>
          <button className="t-btn t-btn-primary t-btn-sm" onClick={handleAdd} style={{ fontSize: 11 }}>Add</button>
        </div>
      </div>
      {entries.length === 0 ? (
        <EmptyState icon="~" title="Waitlist is empty" description="No one has joined the waitlist yet." />
      ) : (
        <div className="t-panel" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(139,92,246,0.12)' }}>
                <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>NAME</th>
                <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>EMAIL</th>
                <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>DATE JOINED</th>
                <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>STATUS</th>
                <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <tr key={e.email} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 600, color: '#f0f0f5' }}>{e.name}</td>
                  <td style={{ padding: '8px 12px', color: '#8888a0' }}>{e.email}</td>
                  <td style={{ padding: '8px 12px', textAlign: 'center', color: '#555570', fontSize: 10 }}>{e.date}</td>
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      padding: '2px 8px', borderRadius: 4, fontSize: 9, fontWeight: 600,
                      background: e.status === 'Approved' ? 'rgba(34,197,94,0.15)' : e.status === 'Rejected' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
                      color: e.status === 'Approved' ? '#22c55e' : e.status === 'Rejected' ? '#ef4444' : '#f59e0b',
                    }}>{e.status}</span>
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                      {e.status === 'Pending' && (
                        <>
                          <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => handleApprove(e.email)} style={{ fontSize: 9, color: '#22c55e' }}>Approve</button>
                          <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => handleReject(e.email)} style={{ fontSize: 9, color: '#ef4444' }}>Reject</button>
                        </>
                      )}
                      {e.status !== 'Pending' && <span style={{ fontSize: 9, color: '#555570' }}>—</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ApprovalsSection() {
  const { toast } = useToast()
  const [approved, setApproved] = useState<ApprovalEntry[]>([
    { email: 'user2@example.com', name: 'Jane Smith', code: 'aB3xK7wQ' },
  ])

  const handleSendInvite = useCallback((email: string) => { toast('success', `Invite email sent to ${email}`) }, [toast])
  const handleRemove = useCallback((email: string) => { setApproved(prev => prev.filter(e => e.email !== email)); toast('info', `Access removed for ${email}`) }, [toast])

  if (approved.length === 0) {
    return <EmptyState icon="!" title="No approved users" description="Approve users from the waitlist to see them here." />
  }

  return (
    <div className="t-panel" style={{ padding: 0, overflow: 'hidden' }}>
      <table className="t-table" style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid rgba(139,92,246,0.12)' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>NAME</th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>EMAIL</th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>INVITE CODE</th>
            <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#8888a0', fontSize: 9 }}>ACTIONS</th>
          </tr>
        </thead>
        <tbody>
          {approved.map(a => (
            <tr key={a.email} style={{ borderBottom: '1px solid rgba(139,92,246,0.06)' }}>
              <td style={{ padding: '8px 12px', fontWeight: 600, color: '#f0f0f5' }}>{a.name}</td>
              <td style={{ padding: '8px 12px', color: '#8888a0' }}>{a.email}</td>
              <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.05em', color: '#22d3ee' }}>{a.code}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                  <button className="t-btn t-btn-sm t-btn-ghost" onClick={() => handleSendInvite(a.email)} style={{ fontSize: 9 }}>Send Invite Email</button>
                  <button className="t-btn t-btn-sm t-btn-danger" onClick={() => handleRemove(a.email)} style={{ fontSize: 9 }}>Remove Access</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/lib/use-toast'
import { useAuth } from '@/lib/auth-context'

declare global {
  interface Window {
    __captured_console_errors?: string[]
  }
}

function getBrowserInfo(): string {
  if (typeof navigator === 'undefined') return ''
  const ua = navigator.userAgent
  const match = ua.match(/(Chrome|Firefox|Safari|Edge)\/([\d.]+)/)
  if (match) return `${match[1]} ${match[2]}`
  return ua.slice(0, 80)
}

function getPageInfo(): string {
  if (typeof window === 'undefined') return ''
  return window.location.pathname + window.location.search
}

function getConsoleErrors(): string[] {
  try {
    return (window as any).__captured_console_errors?.slice(-20) || []
  } catch { return [] }
}

function getAppVersion(): string {
  return process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0'
}

export default function FeedbackButton() {
  const [open, setOpen] = useState(false)
  const [category, setCategory] = useState<'bug' | 'feature'>('bug')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [minimized, setMinimized] = useState(false)
  const { toast } = useToast()
  const { user } = useAuth()
  const formRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const orig = console.error
    const errors: string[] = []
    console.error = (...args: unknown[]) => {
      const msg = args.map(a => String(a).slice(0, 200)).join(' ').slice(0, 500)
      errors.push(msg)
      if (errors.length > 100) errors.splice(0, 20)
      orig.apply(console, args)
    }
    ;(window as any).__captured_console_errors = errors
    return () => { console.error = orig }
  }, [])

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (formRef.current && !formRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const timer = setTimeout(() => document.addEventListener('click', handleClick), 0)
    return () => { clearTimeout(timer); document.removeEventListener('click', handleClick) }
  }, [open])

  const handleSubmit = useCallback(async () => {
    if (!title.trim() && !description.trim()) return
    setSubmitting(true)
    try {
      const metadata = {
        browser: getBrowserInfo(),
        page: getPageInfo(),
        console_errors: getConsoleErrors(),
        app_version: getAppVersion(),
        user_agent: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 200) : '',
        screen: typeof window !== 'undefined' ? `${window.innerWidth}x${window.innerHeight}` : '',
      }
      await api.post('/feedback', { category, title, description, metadata })
      toast('success', category === 'bug' ? 'Bug report submitted' : 'Feature request submitted')
      setTitle('')
      setDescription('')
      setOpen(false)
    } catch {
      toast('error', 'Failed to submit feedback. Try again.')
    } finally {
      setSubmitting(false)
    }
  }, [category, title, description, toast])

  return (
    <>
      <button
        onClick={() => { setOpen(true); setMinimized(false) }}
        title="Report a bug"
        style={{
          position: 'fixed', bottom: 40, right: 16, zIndex: 9999,
          width: 40, height: 40, borderRadius: '50%',
          background: 'var(--violet)', border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 2px 12px rgba(139,92,246,0.4)',
          transition: 'transform 0.2s',
          color: '#fff',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
      </button>

      {open && (
        <div ref={formRef} style={{
          position: 'fixed', bottom: 88, right: 16, zIndex: 9999,
          width: 340, maxHeight: 460,
          background: 'var(--panel)', border: '1px solid var(--border)',
          borderRadius: 12, boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 14px', borderBottom: '1px solid var(--border)',
            fontSize: 12, fontWeight: 600,
          }}>
            <span>Report a Bug</span>
            <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', fontSize: 16, padding: 0, lineHeight: 1 }}>✕</button>
          </div>

          <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border)' }}>
            {(['bug', 'feature'] as const).map(c => (
              <button key={c} onClick={() => setCategory(c)} style={{
                flex: 1, padding: '8px', fontSize: 11, fontWeight: category === c ? 600 : 400,
                background: 'none', border: 'none', borderBottom: category === c ? '2px solid var(--violet)' : '2px solid transparent',
                color: category === c ? 'var(--violet)' : 'var(--text-faint)', cursor: 'pointer',
                fontFamily: 'inherit',
              }}>{c === 'bug' ? 'Bug' : 'Feature'}</button>
            ))}
          </div>

          <div style={{ padding: '10px 14px', flex: 1, display: 'flex', flexDirection: 'column', gap: 8, overflow: 'auto' }}>
            <input
              className="t-input"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Brief title"
              style={{ width: '100%', fontSize: 11, padding: '6px 8px' }}
            />
            <textarea
              className="t-input"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Describe the issue..."
              style={{ width: '100%', minHeight: 80, fontSize: 11, padding: '6px 8px', resize: 'vertical' }}
            />
            <div style={{ fontSize: 9, color: 'var(--text-faint)', lineHeight: 1.4 }}>
              Will attach: browser, page, console errors, app version
            </div>
          </div>

          <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="t-btn t-btn-primary t-btn-sm"
              onClick={handleSubmit}
              disabled={(!title.trim() && !description.trim()) || submitting}
              style={{ fontSize: 11 }}
            >
              {submitting ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </>
  )
}

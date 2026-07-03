'use client'

import { useState, useRef, useEffect } from 'react'
import { api } from '@/lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const SUGGESTIONS = [
  'Why was my order rejected?',
  'Explain today\'s PnL.',
  'How much risk am I taking?',
  'Which strategy performed best?',
  'Explain today\'s market.',
]

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Hi, I\'m your AI Copilot. Ask me anything about your trading platform — orders, positions, risk, strategies, backtests, or market data.' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (content: string) => {
    if (!content.trim() || loading) return

    setShowSuggestions(false)
    const userMsg: Message = { role: 'user', content }
    const updated = [...messages, userMsg]
    setMessages(updated)
    setInput('')
    setLoading(true)

    try {
      const result = await api.ai.copilot(updated.map(m => ({ role: m.role, content: m.content })))
      setMessages(prev => [...prev, { role: 'assistant', content: result.response }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)' }}>
      <div style={{ marginBottom: 16 }}>
        <h1 className="t-page-title" style={{ margin: 0, fontSize: 18 }}>AI Copilot</h1>
        <p className="t-sub" style={{ fontSize: 11, margin: '2px 0 0' }}>
          Ask questions about your account, orders, risk, strategies, and market.
        </p>
      </div>

      <div style={{
        flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8,
        paddingRight: 4, marginBottom: 12,
      }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '75%',
              padding: '10px 14px',
              borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
              background: msg.role === 'user' ? 'var(--violet)' : 'var(--panel)',
              color: msg.role === 'user' ? '#fff' : 'var(--text)',
              border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
              fontSize: 13,
              lineHeight: 1.5,
              whiteSpace: 'pre-wrap',
            }}>
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
            <div style={{
              padding: '10px 14px', borderRadius: '16px 16px 16px 4px',
              background: 'var(--panel)', border: '1px solid var(--border)',
              fontSize: 13, display: 'flex', gap: 4,
            }}>
              <span style={{ animation: 'pulse 1.2s infinite', opacity: 0.4 }}>●</span>
              <span style={{ animation: 'pulse 1.2s infinite 0.2s', opacity: 0.4 }}>●</span>
              <span style={{ animation: 'pulse 1.2s infinite 0.4s', opacity: 0.4 }}>●</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {showSuggestions && messages.length === 1 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
          {SUGGESTIONS.map(s => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              style={{
                padding: '6px 12px', fontSize: 11, borderRadius: 20,
                background: 'var(--panel)', border: '1px solid var(--border)',
                color: 'var(--text-sub)', cursor: 'pointer', fontFamily: 'inherit',
                transition: 'all 0.15s',
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
        <input
          ref={inputRef}
          className="t-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
          placeholder="Ask anything about your platform..."
          disabled={loading}
          style={{ flex: 1, fontSize: 12 }}
        />
        <button
          className="t-btn t-btn-primary"
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || loading}
          style={{ fontSize: 12, padding: '6px 16px' }}
        >
          Send
        </button>
      </div>
    </div>
  )
}

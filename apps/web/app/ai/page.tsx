'use client'

import { useState, useRef, useEffect } from 'react'
import { api } from '@/lib/api'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  id: string
  intent?: string
  data?: any
}

const QUICK_ACTIONS = [
  { label: 'Market Analysis', prompt: 'Analyze current market conditions for NIFTY and BANKNIFTY' },
  { label: 'Strategy Tips', prompt: 'Suggest trading strategies for high volatility days' },
  { label: 'Build Strategy', prompt: 'Build me an EMA crossover strategy with trailing stop loss for NIFTY' },
  { label: 'Check Risk', prompt: 'Review my risk settings and suggest improvements' },
]

function StrategyCard({ strategy, onDeploy }: { strategy: any; onDeploy: () => void }) {
  return (
    <div style={{
      marginTop: 8, padding: 12,
      background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)',
      border: '1px solid var(--border)',
    }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>
        {strategy.name || 'AI Strategy'}
      </div>
      {strategy.description && (
        <div style={{ fontSize: 11, color: 'var(--text-sub)', marginBottom: 8 }}>
          {strategy.description}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, fontSize: 11, color: 'var(--text-sub)', marginBottom: 8, flexWrap: 'wrap' }}>
        <span style={{ background: 'var(--panel)', padding: '2px 6px', borderRadius: 4 }}>
          {strategy.settings?.symbol || 'NIFTY'}
        </span>
        <span style={{ background: 'var(--panel)', padding: '2px 6px', borderRadius: 4 }}>
          {strategy.settings?.interval || '15m'}
        </span>
        <span style={{ background: 'var(--panel)', padding: '2px 6px', borderRadius: 4 }}>
          {strategy.nodes?.length || 0} blocks
        </span>
        <span style={{ background: 'var(--panel)', padding: '2px 6px', borderRadius: 4 }}>
          {strategy.edges?.length || 0} connections
        </span>
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', marginBottom: 8, fontFamily: 'var(--font-mono)' }}>
        {strategy.tags?.join(', ') || ''}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          className="t-btn t-btn-primary"
          style={{ fontSize: 11, padding: '4px 12px' }}
          onClick={onDeploy}
        >
          Deploy Strategy
        </button>
        <button
          className="t-btn"
          style={{ fontSize: 11, padding: '4px 12px' }}
          onClick={() => {
            navigator.clipboard.writeText(JSON.stringify(strategy, null, 2))
          }}
        >
          Copy JSON
        </button>
      </div>
    </div>
  )
}

export default function AIPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: "Namaste! Main hoon aapka AI Copilot. Market analysis, strategy suggestions, trading commands, ya apne account ki koi bhi baat poochh sakte hain. Kya help chahiye?",
      id: 'welcome',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')

    const userMsg: ChatMessage = { role: 'user', content: msg, id: `user-${Date.now()}` }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const result = await api.ai.chat([
        ...messages.map(m => ({ role: m.role, content: m.content })),
        { role: 'user', content: msg },
      ])
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.response,
        id: `ai-${Date.now()}`,
        intent: result.intent,
        data: result.data,
      }])
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, koi error aa gaya. Phir se try karein.',
        id: `ai-${Date.now()}`,
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleDeploy = () => {
    window.open('/dashboard?tab=user-strategies', '_blank')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div>
        <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>
          AI Assistant
        </h1>
        <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>
          Chat, command, ya strategy banao — sab ek jagah
        </p>
      </div>

      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        {/* Chat Panel */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          background: 'var(--panel)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)', overflow: 'hidden',
        }}>
          {/* Intent indicator + Quick Actions */}
          <div style={{
            padding: '8px 12px', borderBottom: '1px solid var(--border)',
            display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center',
          }}>
            {QUICK_ACTIONS.map(action => (
              <button key={action.label} className="t-chip" onClick={() => handleSend(action.prompt)} disabled={loading}>
                {action.label}
              </button>
            ))}
          </div>

          {/* Messages */}
          <div style={{
            flex: 1, overflowY: 'auto', padding: 12,
            display: 'flex', flexDirection: 'column', gap: 8,
          }}>
            {messages.map(msg => (
              <div key={msg.id}>
                <div style={{
                  display: 'flex', gap: 8,
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}>
                  {msg.role === 'assistant' && (
                    <div style={{
                      width: 24, height: 24, borderRadius: '50%',
                      background: 'var(--gradient-primary)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, flexShrink: 0, color: '#fff', fontWeight: 700,
                    }}>AI</div>
                  )}
                  <div style={{
                    maxWidth: '80%', padding: '8px 12px',
                    borderRadius: msg.role === 'user'
                      ? 'var(--radius-md) var(--radius-md) 0 var(--radius-md)'
                      : 'var(--radius-md) var(--radius-md) var(--radius-md) 0',
                    background: msg.role === 'user' ? 'rgba(0,212,255,0.1)' : 'var(--bg-tertiary)',
                    border: `1px solid ${msg.role === 'user' ? 'rgba(0,212,255,0.15)' : 'var(--border)'}`,
                    fontSize: 12, lineHeight: 1.5, color: 'var(--text)',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {msg.content}
                    {msg.intent === 'build_strategy' && msg.data?.strategy && (
                      <StrategyCard strategy={msg.data.strategy} onDeploy={handleDeploy} />
                    )}
                  </div>
                  {msg.role === 'user' && (
                    <div style={{
                      width: 24, height: 24, borderRadius: '50%',
                      background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, flexShrink: 0, color: 'var(--text-sub)', fontWeight: 700,
                    }}>U</div>
                  )}
                </div>
                {msg.role === 'assistant' && msg.intent === 'desk' && msg.data?.needs_confirmation && (
                  <div style={{ display: 'flex', gap: 6, marginTop: 4, marginLeft: 32 }}>
                    <button
                      className="t-btn t-btn-primary"
                      style={{ fontSize: 10, padding: '2px 10px' }}
                      onClick={() => handleSend(`Yes, confirm: ${msg.content}`)}
                    >
                      Confirm
                    </button>
                    <button
                      className="t-btn"
                      style={{ fontSize: 10, padding: '2px 10px' }}
                      onClick={() => {}}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ display: 'flex', gap: 8 }}>
                <div style={{
                  width: 24, height: 24, borderRadius: '50%',
                  background: 'var(--gradient-primary)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, flexShrink: 0, color: '#fff', fontWeight: 700,
                }}>AI</div>
                <div style={{
                  padding: '8px 12px', borderRadius: 'var(--radius-md) var(--radius-md) var(--radius-md) 0',
                  background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                  fontSize: 12, color: 'var(--text-faint)',
                }}>
                  <span style={{ animation: 't-pulse 2s infinite' }}>Thinking...</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div style={{
            padding: '8px 12px', borderTop: '1px solid var(--border)',
            display: 'flex', gap: 8,
          }}>
            <input
              className="t-input"
              placeholder="Poochhiye kuch bhi — market, strategy, command, ya strategy banao..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }}}
            />
            <button className="t-btn t-btn-primary" onClick={() => handleSend()} disabled={loading || !input.trim()}>
              Send
            </button>
          </div>
        </div>

        {/* Right Panel */}
        <div style={{
          width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div className="t-panel" style={{ padding: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>What I Can Do</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11, color: 'var(--text-sub)' }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--cyan)', fontSize: 10, marginTop: 2 }}>💬</span>
                <div><strong style={{ color: 'var(--text)' }}>Chat</strong> — Market analysis, strategy tips, psychology coaching, platform help</div>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--cyan)', fontSize: 10, marginTop: 2 }}>⚡</span>
                <div><strong style={{ color: 'var(--text)' }}>Commands</strong> — "Show my positions", "Square off", "Why rejected?", "P&L kya hai"</div>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--cyan)', fontSize: 10, marginTop: 2 }}>🤖</span>
                <div><strong style={{ color: 'var(--text)' }}>Build Strategy</strong> — "EMA crossover banao", "Bollinger Bandit strategy for BANKNIFTY" (Enterprise)</div>
              </div>
            </div>
          </div>

          <div className="t-panel" style={{ padding: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>Examples</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11, color: 'var(--text-sub)' }}>
              {[
                'Analyze NIFTY for today',
                'Why was my order rejected?',
                'Build me a trend following strategy',
                'Suggest strategy for ₹50,000 capital',
                'How much risk am I taking?',
                'Explain put option in Hinglish',
              ].map((ex, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(ex)}
                  disabled={loading}
                  style={{
                    textAlign: 'left', background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                    padding: '6px 8px', fontSize: 11, color: 'var(--text-sub)',
                    cursor: 'pointer', fontFamily: 'inherit',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-hi)'; e.currentTarget.style.color = 'var(--text)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-sub)' }}
                >
                  → {ex}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

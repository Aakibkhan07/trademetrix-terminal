'use client'

import { useState, useRef, useEffect } from 'react'
import { api } from '@/lib/api'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  id: string
}

const QUICK_ACTIONS = [
  { label: 'Market Analysis', prompt: 'Analyze current market conditions for NIFTY and BANKNIFTY' },
  { label: 'Strategy Tips', prompt: 'Suggest trading strategies for high volatility days' },
  { label: 'Risk Check', prompt: 'Review my risk settings and suggest improvements' },
  { label: 'Trade Review', prompt: 'Review my recent trading performance' },
]

export default function AIPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: "Hello! I'm your AI trading assistant. Ask me anything about markets, strategies, or your account.", id: 'welcome' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState<string | null>(null)
  const [analysing, setAnalysing] = useState(false)
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
      const result = await api.ai.copilot([...messages.map(m => ({ role: m.role, content: m.content })), { role: 'user', content: msg }])
      const reply = (result as { response: string }).response || 'No response'
      setMessages(prev => [...prev, { role: 'assistant', content: reply, id: `ai-${Date.now()}` }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.', id: `ai-${Date.now()}` }])
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyse = async () => {
    setAnalysing(true)
    try {
      const result = await api.ai.journal(7) as { analysis?: { summary?: string } }
      setAnalysis(result?.analysis?.summary || JSON.stringify(result, null, 2))
    } catch {
      setAnalysis('Could not load analysis. Make sure you have recent trading data.')
    } finally {
      setAnalysing(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div>
        <h1 style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 18, margin: 0, color: 'var(--text)' }}>AI Assistant</h1>
        <p style={{ color: 'var(--text-sub)', fontSize: 12, margin: '2px 0 0' }}>
          Chat with AI for market analysis, strategy suggestions, and trade insights
        </p>
      </div>

      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        {/* Chat Panel */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          background: 'var(--panel)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)', overflow: 'hidden',
        }}>
          {/* Quick Actions */}
          <div style={{
            padding: '8px 12px', borderBottom: '1px solid var(--border)',
            display: 'flex', gap: 6, flexWrap: 'wrap',
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
              <div key={msg.id} style={{
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
                  borderRadius: msg.role === 'user' ? 'var(--radius-md) var(--radius-md) 0 var(--radius-md)' : 'var(--radius-md) var(--radius-md) var(--radius-md) 0',
                  background: msg.role === 'user' ? 'rgba(0,212,255,0.1)' : 'var(--bg-tertiary)',
                  border: `1px solid ${msg.role === 'user' ? 'rgba(0,212,255,0.15)' : 'var(--border)'}`,
                  fontSize: 12, lineHeight: 1.5, color: 'var(--text)',
                  whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
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
              placeholder="Ask about markets, strategies, or your account..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }}}
            />
            <button className="t-btn t-btn-primary" onClick={() => handleSend()} disabled={loading || !input.trim()}>
              Send
            </button>
          </div>
        </div>

        {/* Right Panel: Trade Journal */}
        <div style={{
          width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div className="t-panel" style={{ padding: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>Trade Journal Analysis</div>
            <p style={{ fontSize: 11, color: 'var(--text-sub)', margin: '0 0 10px', lineHeight: 1.4 }}>
              Get AI-powered psychological and statistical feedback on your recent trades.
            </p>
            <button className="t-btn t-btn-primary" onClick={handleAnalyse} disabled={analysing} style={{ width: '100%' }}>
              {analysing ? 'Analyzing...' : 'Analyze Last 7 Days'}
            </button>

            {analysis && (
              <div style={{
                marginTop: 10, padding: 10,
                background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)',
                fontSize: 11, lineHeight: 1.5, color: 'var(--text-sub)',
                whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto',
              }}>
                {analysis}
              </div>
            )}
          </div>

          <div className="t-panel" style={{ padding: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>Capabilities</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11, color: 'var(--text-sub)' }}>
              {[
                'Market analysis & insights',
                'Strategy recommendations',
                'Risk assessment',
                'Trade journal analysis',
                'Technical indicator help',
                'Portfolio review',
              ].map((cap, i) => (
                <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ color: 'var(--cyan)', fontSize: 10 }}>◆</span>
                  {cap}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

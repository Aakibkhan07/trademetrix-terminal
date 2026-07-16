'use client'

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface Toast {
  id: string
  type: ToastType
  message: string
  duration?: number
}

interface ToastContextType {
  toasts: Toast[]
  toast: (type: ToastType, message: string, duration?: number) => void
  removeToast: (id: string) => void
}

const ToastContext = createContext<ToastContextType>({
  toasts: [],
  toast: () => {},
  removeToast: () => {},
})

let toastCounter = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = useCallback((type: ToastType, message: string, duration = 4000) => {
    const id = `toast-${++toastCounter}`
    setToasts(prev => [...prev, { id, type, message, duration }])
  }, [])

  return (
    <ToastContext.Provider value={{ toasts, toast, removeToast }}>
      {children}
      <div className="t-toast-container">
        {toasts.map(t => (
          <ToastItem key={t.id} toast={t} onRemove={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const icon = {
    success: '✓',
    error: '✕',
    info: 'i',
    warning: '!',
  }[toast.type]

  return (
    <div
      className={`t-toast t-toast-${toast.type}`}
      onClick={() => onRemove(toast.id)}
    >
      <span className="t-toast-icon">{icon}</span>
      <span className="t-toast-message">{toast.message}</span>
    </div>
  )
}

export function useToast() {
  return useContext(ToastContext)
}

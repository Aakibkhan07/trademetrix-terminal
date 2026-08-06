'use client'

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { ToastItem } from '@/components/ui/toast'

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
      <div className="t-toast-container" role="status" aria-live="polite" aria-label="Notifications">
        {toasts.map(t => (
          <ToastItem key={t.id} type={t.type} message={t.message} onRemove={() => removeToast(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}

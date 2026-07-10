'use client'

import { create } from 'zustand'

export interface Toast {
  id: string
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
}

export type Theme = 'dark' | 'light'

export interface UIState {
  sidebarCollapsed: boolean
  theme: Theme
  toasts: Toast[]
  toggleSidebar: () => void
  setTheme: (theme: Theme) => void
  addToast: (type: Toast['type'], message: string, duration?: number) => void
  removeToast: (id: string) => void
}

const getInitialTheme = (): Theme => {
  if (typeof window !== 'undefined') {
    return (localStorage.getItem('theme') as Theme) || 'dark'
  }
  return 'dark'
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarCollapsed: false,
  theme: getInitialTheme(),
  toasts: [],

  toggleSidebar: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  setTheme: (theme) => {
    localStorage.setItem('theme', theme)
    document.documentElement.setAttribute('data-theme', theme)
    set({ theme })
  },

  addToast: (type, message, duration = 4000) => {
    const id = Date.now().toString(36)
    set(s => ({ toasts: [...s.toasts, { id, type, message }] }))
    if (duration > 0) {
      setTimeout(() => get().removeToast(id), duration)
    }
  },

  removeToast: (id) => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
}))

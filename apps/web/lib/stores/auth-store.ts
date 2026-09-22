'use client'

import { create } from 'zustand'
import { api } from '@/lib/api'

export interface User {
  id?: string
  email: string
  full_name?: string
  subscription_tier?: string
  is_admin?: boolean
}

export interface AuthState {
  user: User | null
  loading: boolean
  hasSession: boolean
  tier: string
  isAdmin: boolean
  signin: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, full_name?: string) => Promise<void>
  signout: () => Promise<void>
  fetchUser: () => Promise<void>
  setUser: (user: User | null) => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: true,
  hasSession: false,
  tier: 'free',
  isAdmin: false,

  fetchUser: async () => {
    try {
      const u = await api.auth.me()
      const user = u as User
      set({ user, loading: false, hasSession: true, tier: user.subscription_tier || 'free', isAdmin: user.is_admin === true })
    } catch (err: any) {
      // Only clear session on 401 — network blips, 429, 5xx are not proof of invalid session.
      if (err?.status === 401) {
        set({ user: null, loading: false, hasSession: false })
      }
      // Otherwise keep existing state; the ambient error is logged but doesn't kill the session.
    }
  },

  signin: async (email: string, password: string) => {
    const data = await api.auth.signin({ email, password }) as { access_token: string; user?: User }
    if (data.user) {
      const user = data.user as User
      set({ user, hasSession: true, tier: user.subscription_tier || 'free', isAdmin: user.is_admin === true })
    } else {
      await get().fetchUser()
    }
  },

  signup: async (email: string, password: string, full_name?: string) => {
    const data = await api.auth.signup({ email, password, full_name }) as { access_token: string; user?: User }
    if (data.user) {
      const user = data.user as User
      set({ user, hasSession: true, tier: user.subscription_tier || 'free', isAdmin: user.is_admin === true })
    } else {
      await get().fetchUser()
    }
  },

  signout: async () => {
    try {
      await api.auth.signout()
    } catch (e) { console.error('Failed to sign out', e) }
    set({ user: null, hasSession: false, tier: 'free', isAdmin: false })
  },

  setUser: (user) => set({ user, hasSession: user !== null, tier: user?.subscription_tier || 'free', isAdmin: user?.is_admin === true }),
}))

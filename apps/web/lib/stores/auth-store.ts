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
  token: boolean
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
  token: false,
  tier: 'free',
  isAdmin: false,

  fetchUser: async () => {
    try {
      const u = await api.auth.me()
      const user = u as User
      set({ user, loading: false, token: true, tier: user.subscription_tier || 'free', isAdmin: user.is_admin === true })
    } catch {
      set({ user: null, loading: false, token: false })
    }
  },

  signin: async (email: string, password: string) => {
    const data = await api.auth.signin({ email, password }) as { access_token: string; user?: User }
    if (data.user) {
      const user = data.user as User
      set({ user, token: true, tier: user.subscription_tier || 'free', isAdmin: user.is_admin === true })
    } else {
      await get().fetchUser()
    }
  },

  signup: async (email: string, password: string, full_name?: string) => {
    const data = await api.auth.signup({ email, password, full_name }) as { access_token: string; user?: User }
    if (data.user) {
      const user = data.user as User
      set({ user, token: true, tier: user.subscription_tier || 'free', isAdmin: user.is_admin === true })
    } else {
      await get().fetchUser()
    }
  },

  signout: async () => {
    try {
      await api.auth.signout()
    } catch { }
    set({ user: null, token: false, tier: 'free', isAdmin: false })
  },

  setUser: (user) => set({ user, token: user !== null, tier: user?.subscription_tier || 'free', isAdmin: user?.is_admin === true }),
}))

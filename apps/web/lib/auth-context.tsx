'use client'

import { createContext, useContext, useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { api } from './api'

export interface User {
  id?: string
  email: string
  full_name?: string
  subscription_tier?: string
  is_admin?: boolean
}

export interface AuthContextType {
  token: boolean
  user: User | null
  tier: string
  isAdmin: boolean
  signin: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, full_name?: string) => Promise<void>
  signout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  const tier = user?.subscription_tier || 'free'
  const isAdmin = user?.is_admin === true
  const token: boolean = user !== null

  const fetchUser = useCallback(async () => {
    try {
      const u = await api.auth.me()
      setUser(u as User)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUser()
  }, [fetchUser])

  const signin = useCallback(async (email: string, password: string) => {
    const data = await api.auth.signin({ email, password }) as { access_token: string; user?: User }
    if (data.user) {
      setUser(data.user as User)
    } else {
      await fetchUser()
    }
  }, [fetchUser])

  const signup = useCallback(async (email: string, password: string, full_name?: string) => {
    const data = await api.auth.signup({ email, password, full_name }) as { access_token: string; user?: User }
    if (data.user) {
      setUser(data.user as User)
    } else {
      await fetchUser()
    }
  }, [fetchUser])

  const signout = useCallback(async () => {
    try {
      await api.auth.signout()
    } catch {
      // ignore — we clear local state regardless
    }
    setUser(null)
    router.push('/auth')
  }, [router])

  const value = useMemo<AuthContextType>(() => ({
    token, user, tier, isAdmin, signin, signup, signout, loading,
  }), [token, user, tier, isAdmin, signin, signup, signout, loading])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

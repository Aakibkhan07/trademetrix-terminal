'use client'

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { api } from './api'

interface User {
  id?: string
  email: string
  full_name?: string
}

interface AuthContextType {
  token: string | null
  user: User | null
  signin: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, full_name?: string) => Promise<void>
  signout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

const TOKEN_KEY = 'trademetrix_token'
const USER_KEY = 'trademetrix_user'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY)
    const storedUser = localStorage.getItem(USER_KEY)
    if (stored) {
      setToken(stored)
      if (storedUser) {
        try { setUser(JSON.parse(storedUser)) } catch { /* ignore */ }
      }
    }
    setLoading(false)
  }, [])

  const persist = useCallback((t: string, u: User) => {
    setToken(t)
    setUser(u)
    localStorage.setItem(TOKEN_KEY, t)
    localStorage.setItem(USER_KEY, JSON.stringify(u))
    api.setToken(t)
  }, [])

  const signin = useCallback(async (email: string, password: string) => {
    const data = await api.auth.signin({ email, password }) as { access_token: string; user?: User }
    persist(data.access_token, data.user || { email })
  }, [persist])

  const signup = useCallback(async (email: string, password: string, full_name?: string) => {
    const data = await api.auth.signup({ email, password, full_name }) as { access_token: string; user?: User }
    persist(data.access_token, data.user || { email, full_name })
  }, [persist])

  const signout = useCallback(() => {
    setToken(null)
    setUser(null)
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    api.setToken(null)
    router.push('/auth')
  }, [router])

  return (
    <AuthContext.Provider value={{ token, user, signin, signup, signout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

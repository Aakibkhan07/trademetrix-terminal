'use client'

import { useEffect, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '@/lib/auth-context'
import { MarketDataProvider } from '@/lib/use-market-data'
import { ToastProvider } from '@/lib/use-toast'
import { useAuthStore } from '@/lib/stores/auth-store'
import { useUIStore } from '@/lib/stores/ui-store'
import type { ReactNode } from 'react'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function StoreInitializer() {
  const fetchUser = useAuthStore(s => s.fetchUser)
  const setTheme = useUIStore(s => s.setTheme)
  const theme = useUIStore(s => s.theme)

  useEffect(() => {
    fetchUser()
  }, [fetchUser])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    setTheme(theme)
  }, [])

  return null
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MarketDataProvider>
          <ToastProvider>
            <StoreInitializer />
            {children}
          </ToastProvider>
        </MarketDataProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}

'use client'

import { AuthProvider } from '@/lib/auth-context'
import { MarketDataProvider } from '@/lib/use-market-data'
import { ToastProvider } from '@/lib/use-toast'
import type { ReactNode } from 'react'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <MarketDataProvider>
        <ToastProvider>
          {children}
        </ToastProvider>
      </MarketDataProvider>
    </AuthProvider>
  )
}

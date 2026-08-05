import type { Metadata } from 'next'
import { Outfit, DM_Sans } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import AppLayout from '@/components/app-layout'
import ClarityScript from '@/components/clarity'
import AnalyticsTracker from '@/components/analytics-tracker'
import FeedbackButtonWrapper from '@/components/feedback-wrapper'
import QuickOrderDrawer from '@/components/quick-order-drawer'

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-display',
})

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-body',
})

export const metadata: Metadata = {
  title: { default: 'TradeMetrix Terminal', template: '%s | TradeMetrix' },
  description: 'Multi-broker algorithmic trading platform with AI-powered strategies, real-time market data, and automated execution.',
  icons: {
    icon: '/favicon.svg',
    shortcut: '/favicon.svg',
  },
  openGraph: {
    title: 'TradeMetrix Terminal',
    description: 'Multi-broker algorithmic trading platform with AI-powered strategies, real-time market data, and automated execution.',
    url: 'https://ai.trademetrix.tech',
    siteName: 'TradeMetrix',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'TradeMetrix Terminal',
    description: 'Multi-broker algorithmic trading platform with AI-powered strategies.',
  },
  robots: { index: true, follow: true },
  keywords: ['trading', 'algorithmic trading', 'stock market', 'broker', 'Fyers', 'Zerodha', 'Angel One', 'automated trading'],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${outfit.variable} ${dmSans.variable}`}>
      <head />
      <body>
        <ClarityScript />
        <Providers>
          <AnalyticsTracker />
          <AppLayout>{children}</AppLayout>
          <FeedbackButtonWrapper />
          <QuickOrderDrawer />
        </Providers>
      </body>
    </html>
  )
}

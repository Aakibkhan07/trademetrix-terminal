import type { Metadata } from 'next'
import { Outfit, DM_Sans } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import AppLayout from '@/components/app-layout'
import ClarityScript from '@/components/clarity'
import FeedbackButtonWrapper from '@/components/feedback-wrapper'

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
  title: 'TradeMetrix Terminal',
  description: 'Multi-broker algorithmic trading platform',
  icons: {
    icon: '/favicon.svg',
    shortcut: '/favicon.svg',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${outfit.variable} ${dmSans.variable}`}>
      <head />
      <body>
        <ClarityScript />
        <Providers>
          <AppLayout>{children}</AppLayout>
          <FeedbackButtonWrapper />
        </Providers>
      </body>
    </html>
  )
}

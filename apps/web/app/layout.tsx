import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'
import AppLayout from '@/components/app-layout'
import ClarityScript from '@/components/clarity'
import FeedbackButtonWrapper from '@/components/feedback-wrapper'

export const metadata: Metadata = {
  title: 'Trade Metrix Terminal',
  description: 'Multi-broker algorithmic trading platform',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
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

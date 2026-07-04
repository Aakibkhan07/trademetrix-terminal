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
          href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=Outfit:wght@400;500;600;700&display=swap"
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

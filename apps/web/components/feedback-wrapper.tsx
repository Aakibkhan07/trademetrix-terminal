'use client'

import dynamic from 'next/dynamic'

const FeedbackButton = dynamic(() => import('@/components/feedback-button'), { ssr: false })

export default function FeedbackButtonWrapper() {
  return <FeedbackButton />
}

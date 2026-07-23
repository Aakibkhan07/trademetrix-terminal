'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function CopilotRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace('/ai') }, [router])
  return null
}

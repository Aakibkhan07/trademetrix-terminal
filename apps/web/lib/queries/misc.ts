'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useBrokerCredentials() {
  return useQuery({
    queryKey: ['broker-credentials'],
    queryFn: () => api.brokers.credentials(),
    staleTime: 30_000,
  })
}

export function useBrokerList() {
  return useQuery({
    queryKey: ['broker-list'],
    queryFn: () => api.brokers.list(),
    staleTime: 300_000,
  })
}

export function useMarketplaceStrategies() {
  return useQuery({
    queryKey: ['marketplace-strategies'],
    queryFn: () => api.strategies.list(),
    staleTime: 60_000,
  })
}

export function useRiskSettings() {
  return useQuery({
    queryKey: ['risk-settings'],
    queryFn: () => api.risk.settings(),
    staleTime: 30_000,
  })
}

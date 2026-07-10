'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useOrders() {
  return useQuery({
    queryKey: ['orders'],
    queryFn: () => api.engine.orders(),
    refetchInterval: 10_000,
    staleTime: 5_000,
  })
}

export function usePositions() {
  return useQuery({
    queryKey: ['positions'],
    queryFn: () => api.engine.positions(),
    refetchInterval: 15_000,
    staleTime: 5_000,
  })
}

export function useFunds() {
  return useQuery({
    queryKey: ['funds'],
    queryFn: () => api.engine.funds(),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
}

export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: () => api.engine.runs(),
    staleTime: 10_000,
  })
}

export function useCancelOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (orderId: string) => api.engine.cancelOrder(orderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['orders'] }),
  })
}

export function useExecuteTrade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: any) => api.engine.trade(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['orders'] })
      qc.invalidateQueries({ queryKey: ['positions'] })
    },
  })
}

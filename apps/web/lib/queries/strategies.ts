'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useUserStrategies(statusFilter?: string) {
  return useQuery({
    queryKey: ['user-strategies', statusFilter],
    queryFn: () => api.userStrategies.list(statusFilter),
    staleTime: 10_000,
  })
}

export function useUserStrategy(id: string) {
  return useQuery({
    queryKey: ['user-strategy', id],
    queryFn: () => api.userStrategies.get(id),
    enabled: !!id,
    staleTime: 5_000,
  })
}

export function useCreateUserStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: any) => api.userStrategies.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['user-strategies'] }),
  })
}

export function useUpdateUserStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => api.userStrategies.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['user-strategies'] })
      qc.invalidateQueries({ queryKey: ['user-strategy'] })
    },
  })
}

export function useDeleteUserStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.userStrategies.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['user-strategies'] }),
  })
}

export function useDeployUserStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: string }) => api.userStrategies.deploy(id, mode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['user-strategies'] })
      qc.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useMarketplaceStrategies() {
  return useQuery({
    queryKey: ['marketplace-strategies'],
    queryFn: () => api.strategies.list(),
    staleTime: 60_000,
  })
}

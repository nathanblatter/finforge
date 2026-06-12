import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import type { MonteCarloRequest } from '../types'

export function useFrontier(enabled = true) {
  return useQuery({
    queryKey: ['quant', 'frontier'],
    queryFn: api.getFrontier,
    enabled,
    staleTime: 15 * 60 * 1000,
    retry: 1,
  })
}

export function useClusters(threshold = 0.65, enabled = true) {
  return useQuery({
    queryKey: ['quant', 'clusters', threshold],
    queryFn: () => api.getClusters(threshold),
    enabled,
    staleTime: 15 * 60 * 1000,
    retry: 1,
  })
}

export function useIvHv(enabled = true) {
  return useQuery({
    queryKey: ['quant', 'ivhv'],
    queryFn: () => api.getIvHv(),
    enabled,
    staleTime: 15 * 60 * 1000,
    retry: 1,
  })
}

export function useMonteCarlo() {
  return useMutation({
    mutationFn: (body: MonteCarloRequest) => api.runMonteCarlo(body),
  })
}

export function useRegime() {
  return useQuery({
    queryKey: ['quant', 'regime'],
    queryFn: api.getRegime,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  })
}

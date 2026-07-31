import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { FireSettingsUpdate, FireMonteCarloRequest, SwrRequest } from '../types'

export function useFireSettings() {
  return useQuery({
    queryKey: ['fire', 'settings'],
    queryFn: api.getFireSettings,
    staleTime: 5 * 60 * 1000,
  })
}

export function useUpdateFireSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: FireSettingsUpdate) => api.updateFireSettings(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fire'] })
    },
  })
}

export function useFireSummary(enabled = true) {
  return useQuery({
    queryKey: ['fire', 'summary'],
    queryFn: api.getFireSummary,
    enabled,
    staleTime: 15 * 60 * 1000,
    retry: 1,
  })
}

export function useFireMonteCarlo() {
  return useMutation({
    mutationFn: (body: FireMonteCarloRequest = {}) => api.runFireMonteCarlo(body),
  })
}

export function useFireSwr() {
  return useMutation({
    mutationFn: (body: SwrRequest = {}) => api.runFireSwr(body),
  })
}

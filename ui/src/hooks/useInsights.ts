import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useInsights() {
  return useQuery({
    queryKey: ['insights'],
    queryFn: api.getInsights,
  })
}

export function useInsightsHistory(limit = 50) {
  return useQuery({
    queryKey: ['insights', 'history', limit],
    queryFn: () => api.getInsightsHistory(limit),
  })
}

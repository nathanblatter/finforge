import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useFinancialHealth() {
  return useQuery({
    queryKey: ['financial-health', 'current'],
    queryFn: () => api.getFinancialHealth(),
    staleTime: 5 * 60 * 1000,
  })
}

export function useFinancialHealthHistory(months = 24) {
  return useQuery({
    queryKey: ['financial-health', 'history', months],
    queryFn: () => api.getFinancialHealthHistory(months),
    staleTime: 5 * 60 * 1000,
  })
}

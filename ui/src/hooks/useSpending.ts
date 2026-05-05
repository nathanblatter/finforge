import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useMonthlySpending(month?: string) {
  return useQuery({
    queryKey: ['spending', 'monthly', month ?? 'current'],
    queryFn: () => api.getMonthlySpending(month),
  })
}

export function useTransactions(params?: { month?: string; category?: string }) {
  return useQuery({
    queryKey: ['spending', 'transactions', params],
    queryFn: () => api.getTransactions(params),
  })
}

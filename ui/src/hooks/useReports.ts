import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useFinancialPreview(period: string, month: string, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ['reports', 'financial', 'preview', period, month, startDate, endDate],
    queryFn: () => api.getFinancialPreview(period, month, startDate, endDate),
    enabled: !!month,
  })
}

export function useTithingIncome(period: string, month: string, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ['reports', 'tithing', 'income', period, month, startDate, endDate],
    queryFn: () => api.getTithingIncome(period, month, startDate, endDate),
    enabled: !!month,
  })
}

export function useContributionPreview(period: string, month: string, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ['reports', 'contributions', 'preview', period, month, startDate, endDate],
    queryFn: () => api.getContributionPreview(period, month, startDate, endDate),
    enabled: !!month,
  })
}

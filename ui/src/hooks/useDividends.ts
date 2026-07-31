import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useDividendIncome() {
  return useQuery({
    queryKey: ['dividends', 'income'],
    queryFn: api.getDividendIncome,
  })
}

export function useDividendCalendar(months = 3) {
  return useQuery({
    queryKey: ['dividends', 'calendar', months],
    queryFn: () => api.getDividendCalendar(months),
  })
}

export function useDividendHistory(symbol?: string) {
  return useQuery({
    queryKey: ['dividends', 'history', symbol ?? null],
    queryFn: () => api.getDividendHistory(symbol),
  })
}

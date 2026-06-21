import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useTaxSummary(marginalRate?: number) {
  return useQuery({
    queryKey: ['tax-summary', marginalRate ?? null],
    queryFn: () => api.getTaxSummary(marginalRate),
  })
}

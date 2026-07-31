import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { TaxEstimateSettings } from '../types'

export function useTaxSummary(marginalRate?: number) {
  return useQuery({
    queryKey: ['tax-summary', marginalRate ?? null],
    queryFn: () => api.getTaxSummary(marginalRate),
  })
}

export function useRealizedLots() {
  return useQuery({
    queryKey: ['tax-lots'],
    queryFn: () => api.getRealizedLots(),
  })
}

export function useTaxEstimates(settings: TaxEstimateSettings) {
  return useQuery({
    queryKey: ['tax-estimates', settings],
    queryFn: () => api.getTaxEstimates(settings),
  })
}

export function useForm1099() {
  return useQuery({
    queryKey: ['tax-form1099'],
    queryFn: () => api.getForm1099(),
  })
}

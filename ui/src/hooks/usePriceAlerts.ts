import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export function usePriceAlerts() {
  return useQuery({
    queryKey: ['price-alerts'],
    queryFn: api.getPriceAlerts,
  })
}

export function useCreatePriceAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ symbol, direction, threshold }: { symbol: string; direction: 'above' | 'below'; threshold: number }) =>
      api.createPriceAlert(symbol, direction, threshold),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['price-alerts'] }),
  })
}

export function useDeletePriceAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deletePriceAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['price-alerts'] }),
  })
}

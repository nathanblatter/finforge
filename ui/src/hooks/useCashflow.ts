import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export function useRunway(days = 90) {
  return useQuery({
    queryKey: ['cashflow', 'runway', days],
    queryFn: () => api.getRunway(days),
    staleTime: 30 * 60 * 1000,
    retry: 1,
  })
}

export function useCashflowSettings() {
  return useQuery({
    queryKey: ['cashflow', 'settings'],
    queryFn: api.getCashflowSettings,
  })
}

export function useUpdateCashflowSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ floorAmount, leadTimeDays }: { floorAmount: number; leadTimeDays: number }) =>
      api.updateCashflowSettings(floorAmount, leadTimeDays),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cashflow'] })
    },
  })
}

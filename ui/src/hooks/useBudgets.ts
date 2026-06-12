import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export function useBudgets() {
  return useQuery({
    queryKey: ['budgets'],
    queryFn: api.getBudgets,
  })
}

export function useUpsertBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ category, monthlyLimit }: { category: string; monthlyLimit: number }) =>
      api.upsertBudget(category, monthlyLimit),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budgets'] }),
  })
}

export function useDeleteBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (category: string) => api.deleteBudget(category),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budgets'] }),
  })
}

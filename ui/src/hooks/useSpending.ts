import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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

export function useRecategorize() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, category }: { id: string; category: string }) =>
      api.updateTransactionCategory(id, category),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['spending'] }),
  })
}

export function useCategoryRules() {
  return useQuery({
    queryKey: ['category-rules'],
    queryFn: api.getCategoryRules,
  })
}

export function useCreateCategoryRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ merchant, category }: { merchant: string; category: string }) =>
      api.createCategoryRule(merchant, category),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['category-rules'] })
      qc.invalidateQueries({ queryKey: ['spending'] })
    },
  })
}

export function useDeleteCategoryRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteCategoryRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['category-rules'] }),
  })
}

export function useSubscriptions(months = 6) {
  return useQuery({
    queryKey: ['spending', 'subscriptions', months],
    queryFn: () => api.getSubscriptions(months),
  })
}

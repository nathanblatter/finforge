import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { GoalDetailResponse, GoalCreateBody } from '../types'

export function useGoals() {
  return useQuery({
    queryKey: ['goals'],
    queryFn: api.getGoals,
  })
}

export function useGoal(id: string) {
  return useQuery<GoalDetailResponse>({
    queryKey: ['goals', id],
    queryFn: () => api.getGoal(id),
    enabled: !!id,
  })
}

export function useGoalTemplates() {
  return useQuery({
    queryKey: ['goals', 'templates'],
    queryFn: api.getGoalTemplates,
  })
}

export function useCreateGoal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: GoalCreateBody) => api.createGoal(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['goals'] }),
  })
}

export function useDeleteGoal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteGoal(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['goals'] }),
  })
}

export function useUpdateGoalStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.updateGoalStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['goals'] }),
  })
}

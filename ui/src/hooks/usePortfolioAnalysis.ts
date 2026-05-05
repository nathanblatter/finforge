import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { PortfolioTargetItem, DrawdownPrediction } from '../types'

export function usePortfolioAnalysis() {
  return useQuery({
    queryKey: ['portfolio', 'analysis'],
    queryFn: api.getPortfolioAnalysis,
  })
}

export function usePortfolioTargets() {
  return useQuery({
    queryKey: ['portfolio', 'targets'],
    queryFn: api.getPortfolioTargets,
  })
}

export function useSetPortfolioTargets() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ accountAlias, targets }: { accountAlias: string; targets: PortfolioTargetItem[] }) =>
      api.setPortfolioTargets(accountAlias, targets),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })
}

export function useDrawdownPredictions() {
  return useQuery({
    queryKey: ['portfolio', 'drawdown'],
    queryFn: api.getDrawdownPredictions,
  })
}

export function usePredictDrawdown() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (symbol: string) => api.predictDrawdown(symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio', 'drawdown'] })
    },
  })
}

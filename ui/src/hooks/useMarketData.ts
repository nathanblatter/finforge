import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export function useWatchlists() {
  return useQuery({
    queryKey: ['watchlists'],
    queryFn: () => api.getWatchlists(),
  })
}

export function useWatchlist(id: string | null) {
  return useQuery({
    queryKey: ['watchlist', id],
    queryFn: () => api.getWatchlist(id!),
    enabled: !!id,
  })
}

export function useCreateWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, symbols }: { name: string; symbols?: string[] }) =>
      api.createWatchlist(name, symbols),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlists'] }),
  })
}

export function useDeleteWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteWatchlist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlists'] }),
  })
}

export function useAddSymbol() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, symbol }: { id: string; symbol: string }) =>
      api.addWatchlistSymbol(id, symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlists'] })
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })
}

export function useRemoveSymbol() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, symbol }: { id: string; symbol: string }) =>
      api.removeWatchlistSymbol(id, symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlists'] })
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })
}

export function useOptionsChain(symbol: string | null) {
  return useQuery({
    queryKey: ['options', symbol],
    queryFn: () => api.getOptionsChain(symbol!),
    enabled: !!symbol,
  })
}

export function useQuotes(symbols: string) {
  return useQuery({
    queryKey: ['quotes', symbols],
    queryFn: () => api.getQuotes(symbols),
    enabled: symbols.length > 0,
    refetchInterval: 60_000, // refresh every 60s
  })
}

import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useBrokerage() {
  return useQuery({
    queryKey: ['investments', 'brokerage'],
    queryFn: api.getBrokerage,
  })
}

export function useIRA() {
  return useQuery({
    queryKey: ['investments', 'ira'],
    queryFn: api.getIRA,
  })
}

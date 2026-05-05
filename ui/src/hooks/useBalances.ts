import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useBalances() {
  return useQuery({
    queryKey: ['balances'],
    queryFn: api.getBalances,
  })
}

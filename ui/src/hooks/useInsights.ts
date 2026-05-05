import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useInsights() {
  return useQuery({
    queryKey: ['insights'],
    queryFn: api.getInsights,
  })
}

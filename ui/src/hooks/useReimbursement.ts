import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useReimbursementTransactions(month: string, rentAmount: number, miscTarget: number) {
  return useQuery({
    queryKey: ['reimbursement', month, rentAmount, miscTarget],
    queryFn: () => api.getReimbursementTransactions(month, rentAmount, miscTarget),
    enabled: !!month,
  })
}

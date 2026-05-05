import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export function useAlerts(includeAcknowledged = false) {
  return useQuery({
    queryKey: ['alerts', { includeAcknowledged }],
    queryFn: () => api.getAlerts(includeAcknowledged),
  })
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.acknowledgeAlert(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

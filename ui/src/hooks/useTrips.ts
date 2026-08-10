import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { TripCreateBody, TripUpdateBody } from '../types'

export function useTrips() {
  return useQuery({
    queryKey: ['trips'],
    queryFn: api.getTrips,
    staleTime: 60 * 1000,
  })
}

export function useTrip(id: string | null) {
  return useQuery({
    queryKey: ['trips', id],
    queryFn: () => api.getTrip(id!),
    enabled: !!id,
    staleTime: 60 * 1000,
  })
}

export function useCreateTrip() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TripCreateBody) => api.createTrip(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })
}

export function useUpdateTrip() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: TripUpdateBody }) => api.updateTrip(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })
}

export function useDeleteTrip() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteTrip(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })
}

export function useSetTripTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ tripId, transactionId, included }: {
      tripId: string; transactionId: string; included: boolean
    }) => api.setTripTransaction(tripId, transactionId, included),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })
}

export function useTripCandidates(tripId: string | null, q: string, enabled = false) {
  return useQuery({
    queryKey: ['trips', tripId, 'candidates', q],
    queryFn: () => api.getTripCandidates(tripId!, q || undefined),
    enabled: enabled && !!tripId,
    staleTime: 60 * 1000,
  })
}

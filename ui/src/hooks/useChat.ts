import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ChatMessage } from '../types'

export function useChat() {
  return useMutation({
    mutationFn: ({ message, history }: { message: string; history: ChatMessage[] }) =>
      api.postChat({ message, history }),
  })
}

export function useChatHistory() {
  return useQuery({
    queryKey: ['chat', 'history'],
    queryFn: api.getChatHistory,
    staleTime: Infinity, // history changes only via our own sends/clear
  })
}

export function useClearChatHistory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.clearChatHistory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['chat', 'history'] }),
  })
}

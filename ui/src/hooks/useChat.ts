import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ChatMessage } from '../types'

export function useChat() {
  return useMutation({
    mutationFn: ({ message, history }: { message: string; history: ChatMessage[] }) =>
      api.postChat({ message, history }),
  })
}

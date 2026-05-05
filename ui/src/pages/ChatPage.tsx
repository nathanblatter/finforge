import { useState, useCallback } from 'react'
import Header from '../components/layout/Header'
import SuggestedPrompts from '../components/chat/SuggestedPrompts'
import ChatWindow from '../components/chat/ChatWindow'
import { useChat } from '../hooks/useChat'
import type { ChatMessage } from '../types'

export default function ChatPage() {
  const [history, setHistory] = useState<ChatMessage[]>([])
  const { mutate, isPending } = useChat()

  const handleSend = useCallback((message: string) => {
    // Optimistically add user message
    const userMsg: ChatMessage = { role: 'user', content: message }
    setHistory((prev) => [...prev, userMsg])

    // Send to API with prior history (before this user message)
    mutate(
      { message, history },
      {
        onSuccess: (data) => {
          setHistory((prev) => [
            ...prev,
            { role: 'assistant', content: data.reply },
          ])
        },
        onError: () => {
          setHistory((prev) => [
            ...prev,
            { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' },
          ])
        },
      },
    )
  }, [history, mutate])

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] gap-4">
      <Header title="Ask FinForge" />
      <SuggestedPrompts onSelect={handleSend} disabled={isPending} />
      <div className="flex-1 bg-slate-800 border border-slate-700 rounded-xl p-4 min-h-0">
        <ChatWindow history={history} onSend={handleSend} isLoading={isPending} />
      </div>
    </div>
  )
}

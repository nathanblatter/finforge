import { useState, useCallback, useEffect, useRef } from 'react'
import Header from '../components/layout/Header'
import SuggestedPrompts from '../components/chat/SuggestedPrompts'
import ChatWindow from '../components/chat/ChatWindow'
import ConfirmDialog from '../components/ConfirmDialog'
import { useChat, useChatHistory, useClearChatHistory } from '../hooks/useChat'
import { useToast } from '../components/Toast'
import type { ChatMessage } from '../types'

export default function ChatPage() {
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [confirmClear, setConfirmClear] = useState(false)
  const { mutate, isPending } = useChat()
  const { data: historyData } = useChatHistory()
  const clearHistory = useClearChatHistory()
  const toast = useToast()

  // Seed local history from persisted messages once, on first load.
  const seeded = useRef(false)
  useEffect(() => {
    if (!seeded.current && historyData) {
      setHistory(historyData.messages.map((m) => ({ role: m.role, content: m.content })))
      seeded.current = true
    }
  }, [historyData])

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

  const handleClear = () => {
    setConfirmClear(false)
    clearHistory.mutate(undefined, {
      onSuccess: () => {
        setHistory([])
        toast.success('Chat history cleared')
      },
      onError: (e: any) => toast.error(e?.message ?? 'Failed to clear history'),
    })
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] gap-4">
      <div className="flex items-center justify-between">
        <Header title="Ask FinForge" />
        {history.length > 0 && (
          <button
            onClick={() => setConfirmClear(true)}
            disabled={clearHistory.isPending}
            className="text-xs text-slate-400 hover:text-rose-400 transition-colors disabled:opacity-50"
          >
            Clear history
          </button>
        )}
      </div>
      <SuggestedPrompts onSelect={handleSend} disabled={isPending} />
      <div className="flex-1 bg-slate-800 border border-slate-700 rounded-xl p-4 min-h-0">
        <ChatWindow history={history} onSend={handleSend} isLoading={isPending} />
      </div>

      <ConfirmDialog
        open={confirmClear}
        title="Clear chat history?"
        message="This permanently deletes all saved messages in this conversation. This can't be undone."
        confirmLabel="Clear"
        danger
        onConfirm={handleClear}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  )
}

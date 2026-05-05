import { useState } from 'react'
import Header from '../components/layout/Header'
import WatchlistPanel from '../components/watchlists/WatchlistPanel'
import OptionsChainModal from '../components/watchlists/OptionsChainModal'
import { useWatchlists, useCreateWatchlist, useDeleteWatchlist } from '../hooks/useMarketData'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export default function WatchlistsPage() {
  const { data, isLoading } = useWatchlists()
  const createWatchlist = useCreateWatchlist()
  const deleteWatchlist = useDeleteWatchlist()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [optionsSymbol, setOptionsSymbol] = useState<string | null>(null)

  const watchlists = data?.watchlists ?? []
  const selected = watchlists.find((wl) => wl.id === selectedId) ?? watchlists[0] ?? null

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    createWatchlist.mutate({ name })
    setNewName('')
  }

  return (
    <div className="space-y-6">
      <Header title="Watchlists" />

      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <Skeleton className="h-64" />
          <div className="lg:col-span-3"><Skeleton className="h-64" /></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left — watchlist list */}
          <div className="space-y-3">
            <form onSubmit={handleCreate} className="flex gap-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="New watchlist..."
                className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
              />
              <button
                type="submit"
                disabled={createWatchlist.isPending}
                className="px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                +
              </button>
            </form>

            {watchlists.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-8">
                No watchlists yet — create one above
              </p>
            ) : (
              <div className="space-y-1">
                {watchlists.map((wl) => (
                  <div
                    key={wl.id}
                    className={`flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                      selected?.id === wl.id
                        ? 'bg-slate-700 text-sky-400'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                    }`}
                    onClick={() => setSelectedId(wl.id)}
                  >
                    <span className="text-sm font-medium truncate">{wl.name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">{wl.items.length}</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          deleteWatchlist.mutate(wl.id)
                          if (selectedId === wl.id) setSelectedId(null)
                        }}
                        className="text-slate-600 hover:text-rose-400 transition-colors"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                          fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right — selected watchlist */}
          <div className="lg:col-span-3">
            {selected ? (
              <WatchlistPanel
                watchlist={selected}
                onOptionsClick={setOptionsSymbol}
              />
            ) : (
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center text-slate-500 text-sm">
                Select or create a watchlist to get started
              </div>
            )}
          </div>
        </div>
      )}

      {/* Options chain modal */}
      {optionsSymbol && (
        <OptionsChainModal
          symbol={optionsSymbol}
          onClose={() => setOptionsSymbol(null)}
        />
      )}
    </div>
  )
}

import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { formatCurrency, formatDate } from '../../utils/format'
import { useRecategorize, useCreateCategoryRule, useUpdateTransactionMeta } from '../../hooks/useSpending'
import { useToast } from '../Toast'
import type { TransactionResponse } from '../../types'

export type FeedFilter = { category?: string; card?: string; tag?: string }

interface Props {
  transactions: TransactionResponse[]
  externalFilter?: FeedFilter
  onClearExternal?: (key: keyof FeedFilter) => void
  onSelectTag?: (tag: string) => void
}

const COLS = 6

export default function TransactionFeed({
  transactions,
  externalFilter,
  onClearExternal,
  onSelectTag,
}: Props) {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [hidePending, setHidePending] = useState(false)

  const recategorize = useRecategorize()
  const createRule = useCreateCategoryRule()
  const updateMeta = useUpdateTransactionMeta()
  const toast = useToast()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [applyRule, setApplyRule] = useState(false)
  const [metaId, setMetaId] = useState<string | null>(null)

  const startEdit = (t: TransactionResponse) => {
    setEditingId(t.id)
    setEditValue(t.category ?? '')
    setApplyRule(false)
  }

  const saveEdit = (t: TransactionResponse) => {
    const val = editValue.trim()
    if (!val) { toast.error('Enter a category'); return }
    setEditingId(null)
    if (applyRule && t.merchant_name) {
      createRule.mutate(
        { merchant: t.merchant_name, category: val },
        {
          onSuccess: () => toast.success(`All "${t.merchant_name}" → ${val}`),
          onError: (e: any) => toast.error(e?.message ?? 'Failed to save rule'),
        },
      )
    } else {
      recategorize.mutate(
        { id: t.id, category: val },
        {
          onSuccess: () => toast.success(`Recategorized to ${val}`),
          onError: (e: any) => toast.error(e?.message ?? 'Failed to recategorize'),
        },
      )
    }
  }

  const categories = useMemo(() => {
    const set = new Set<string>()
    transactions.forEach((t) => { if (t.category) set.add(t.category) })
    return Array.from(set).sort()
  }, [transactions])

  const filtered = useMemo(() => {
    return transactions.filter((t) => {
      if (hidePending && t.is_pending) return false
      if (categoryFilter && t.category !== categoryFilter) return false
      if (externalFilter?.category && t.category !== externalFilter.category) return false
      if (externalFilter?.card && t.account_alias !== externalFilter.card) return false
      if (externalFilter?.tag && !t.tags.includes(externalFilter.tag)) return false
      if (search) {
        const q = search.toLowerCase()
        return (
          t.merchant_name?.toLowerCase().includes(q) ||
          t.category?.toLowerCase().includes(q) ||
          t.account_alias.toLowerCase().includes(q) ||
          t.notes?.toLowerCase().includes(q) ||
          t.tags.some((tag) => tag.includes(q))
        )
      }
      return true
    })
  }, [transactions, search, categoryFilter, hidePending, externalFilter])

  const chips: { key: keyof FeedFilter; label: string }[] = []
  if (externalFilter?.category) chips.push({ key: 'category', label: externalFilter.category })
  if (externalFilter?.card) chips.push({ key: 'card', label: externalFilter.card })
  if (externalFilter?.tag) chips.push({ key: 'tag', label: `#${externalFilter.tag}` })

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Transactions</h3>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="text"
          placeholder="Search merchant, category, note, #tag…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[200px] bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={hidePending}
            onChange={(e) => setHidePending(e.target.checked)}
            className="accent-sky-500"
          />
          Hide pending
        </label>
      </div>

      {/* Cross-filter chips */}
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <span className="text-xs text-slate-500">Filtered by chart:</span>
          {chips.map((c) => (
            <button
              key={c.key}
              onClick={() => onClearExternal?.(c.key)}
              className="inline-flex items-center gap-1.5 text-xs bg-sky-500/15 text-sky-300 border border-sky-500/30 rounded-full pl-2.5 pr-1.5 py-0.5 hover:bg-sky-500/25 transition-colors"
            >
              {c.label}
              <span className="text-sky-400/80">✕</span>
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
              <th className="pb-2 pr-4">Date</th>
              <th className="pb-2 pr-4">Merchant</th>
              <th className="pb-2 pr-4">Category</th>
              <th className="pb-2 pr-4">Account</th>
              <th className="pb-2 pr-4 text-right">Amount</th>
              <th className="pb-2 w-8"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={COLS} className="py-8 text-center text-slate-500">
                  No transactions match your filters
                </td>
              </tr>
            ) : (
              filtered.map((t) => (
                <FeedRow
                  key={t.id}
                  t={t}
                  editingId={editingId}
                  editValue={editValue}
                  applyRule={applyRule}
                  setEditValue={setEditValue}
                  setApplyRule={setApplyRule}
                  setEditingId={setEditingId}
                  startEdit={startEdit}
                  saveEdit={saveEdit}
                  metaOpen={metaId === t.id}
                  onToggleMeta={() => setMetaId(metaId === t.id ? null : t.id)}
                  onSaveMeta={(notes, tags) => {
                    updateMeta.mutate(
                      { id: t.id, notes, tags },
                      {
                        onSuccess: () => { toast.success('Saved'); setMetaId(null) },
                        onError: (e: any) => toast.error(e?.message ?? 'Failed to save'),
                      },
                    )
                  }}
                  onSelectTag={onSelectTag}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 text-xs text-slate-600">
        Showing {filtered.length} of {transactions.length} transactions
      </div>
    </div>
  )
}

interface RowProps {
  t: TransactionResponse
  editingId: string | null
  editValue: string
  applyRule: boolean
  setEditValue: (v: string) => void
  setApplyRule: (v: boolean) => void
  setEditingId: (v: string | null) => void
  startEdit: (t: TransactionResponse) => void
  saveEdit: (t: TransactionResponse) => void
  metaOpen: boolean
  onToggleMeta: () => void
  onSaveMeta: (notes: string, tags: string[]) => void
  onSelectTag?: (tag: string) => void
}

function FeedRow({
  t, editingId, editValue, applyRule, setEditValue, setApplyRule,
  setEditingId, startEdit, saveEdit, metaOpen, onToggleMeta, onSaveMeta, onSelectTag,
}: RowProps) {
  const hasMeta = !!t.notes || t.tags.length > 0
  return (
    <>
      <tr className="hover:bg-slate-700/30 transition-colors">
        <td className="py-2.5 pr-4 text-slate-400 whitespace-nowrap align-top">
          {formatDate(t.date)}
        </td>
        <td className="py-2.5 pr-4 text-slate-200 align-top">
          <div className="flex items-center gap-2 flex-wrap">
            {t.merchant_name ? (
              <Link
                to={`/merchant?name=${encodeURIComponent(t.merchant_name)}`}
                className="hover:text-sky-400 transition-colors"
              >
                {t.merchant_name}
              </Link>
            ) : (
              <span className="text-slate-500 italic">Unknown</span>
            )}
            {t.is_pending && (
              <span className="text-xs bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded">Pending</span>
            )}
            {t.is_fixed_expense && (
              <span className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">Fixed</span>
            )}
          </div>
          {(t.tags.length > 0 || t.notes) && (
            <div className="flex items-center gap-1.5 flex-wrap mt-1">
              {t.tags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => onSelectTag?.(tag)}
                  className="text-[11px] bg-violet-500/15 text-violet-300 border border-violet-500/25 rounded-full px-2 py-0.5 hover:bg-violet-500/25 transition-colors"
                >
                  #{tag}
                </button>
              ))}
              {t.notes && (
                <span className="text-[11px] text-slate-500 italic truncate max-w-[220px]" title={t.notes}>
                  “{t.notes}”
                </span>
              )}
            </div>
          )}
        </td>
        <td className="py-2.5 pr-4 text-slate-400 align-top">
          {editingId === t.id ? (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <input
                  autoFocus
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveEdit(t)
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  className="w-32 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs text-slate-100 focus:outline-none focus:border-sky-500"
                />
                <button onClick={() => saveEdit(t)} className="text-xs text-sky-400 hover:text-sky-300">Save</button>
                <button onClick={() => setEditingId(null)} className="text-xs text-slate-500 hover:text-slate-300">Cancel</button>
              </div>
              {t.merchant_name && (
                <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                  <input type="checkbox" checked={applyRule} onChange={(e) => setApplyRule(e.target.checked)} className="accent-sky-500" />
                  Always for "{t.merchant_name}"
                </label>
              )}
            </div>
          ) : (
            <button
              onClick={() => startEdit(t)}
              title="Click to recategorize"
              className="group inline-flex items-center gap-1 hover:text-slate-200 transition-colors"
            >
              <span>{t.category ?? '—'}</span>
              {t.category_overridden && (
                <span className="w-1.5 h-1.5 rounded-full bg-sky-500" title="Manually set" />
              )}
              {t.subcategory && (
                <span className="text-slate-600 text-xs">· {t.subcategory}</span>
              )}
              <svg className="opacity-0 group-hover:opacity-100 transition-opacity" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
              </svg>
            </button>
          )}
        </td>
        <td className="py-2.5 pr-4 text-slate-400 align-top">{t.account_alias}</td>
        <td className="py-2.5 pr-4 text-right font-medium align-top">
          <span className={t.amount < 0 ? 'text-emerald-400' : 'text-slate-100'}>
            {formatCurrency(Math.abs(t.amount))}
          </span>
        </td>
        <td className="py-2.5 text-right align-top">
          <button
            onClick={onToggleMeta}
            title="Notes & tags"
            className={`p-1 rounded transition-colors ${
              hasMeta ? 'text-violet-400 hover:text-violet-300' : 'text-slate-600 hover:text-slate-300'
            }`}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
              <line x1="7" y1="7" x2="7.01" y2="7" />
            </svg>
          </button>
        </td>
      </tr>
      {metaOpen && (
        <tr className="bg-slate-900/40">
          <td colSpan={COLS} className="px-2 py-3">
            <MetaEditor t={t} onSave={onSaveMeta} onCancel={onToggleMeta} />
          </td>
        </tr>
      )}
    </>
  )
}

function MetaEditor({
  t, onSave, onCancel,
}: {
  t: TransactionResponse
  onSave: (notes: string, tags: string[]) => void
  onCancel: () => void
}) {
  const [notes, setNotes] = useState(t.notes ?? '')
  const [tags, setTags] = useState<string[]>(t.tags)
  const [tagInput, setTagInput] = useState('')

  const addTag = (raw: string) => {
    const clean = raw.trim().toLowerCase().replace(/^#/, '').slice(0, 50)
    if (clean && !tags.includes(clean) && tags.length < 10) setTags([...tags, clean])
    setTagInput('')
  }

  return (
    <div className="flex flex-col gap-3 max-w-2xl">
      <div>
        <label className="text-[11px] text-slate-500 uppercase tracking-wider">Tags</label>
        <div className="flex flex-wrap items-center gap-1.5 mt-1">
          {tags.map((tag) => (
            <span key={tag} className="inline-flex items-center gap-1 text-xs bg-violet-500/15 text-violet-300 border border-violet-500/25 rounded-full pl-2 pr-1 py-0.5">
              #{tag}
              <button onClick={() => setTags(tags.filter((x) => x !== tag))} className="text-violet-400/70 hover:text-violet-200">✕</button>
            </span>
          ))}
          <input
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(tagInput) }
              if (e.key === 'Backspace' && !tagInput && tags.length) setTags(tags.slice(0, -1))
            }}
            placeholder={tags.length < 10 ? 'add tag…' : 'max 10'}
            disabled={tags.length >= 10}
            className="bg-slate-900 border border-slate-600 rounded px-2 py-0.5 text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-violet-500 w-28"
          />
        </div>
      </div>
      <div>
        <label className="text-[11px] text-slate-500 uppercase tracking-wider">Note</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="split with roommate, reimbursable, …"
          className="mt-1 w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500 resize-none"
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onSave(notes, tags)}
          className="px-3 py-1.5 text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
        >
          Save
        </button>
        <button onClick={onCancel} className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">Cancel</button>
      </div>
    </div>
  )
}

// Privacy mode masks every currency string app-wide. The flag lives at module
// level so the format helpers stay plain functions; PrivacyProvider keeps it
// in sync and forces a remount so stale strings can't linger.
let privacyMode = false

export function setPrivacyMode(on: boolean) {
  privacyMode = on
}

const MASK = '$•••••'

export function formatCurrency(value: number | string): string {
  if (privacyMode) return MASK
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value))
}

export function formatCurrencyCompact(value: number | string): string {
  if (privacyMode) return MASK
  value = Number(value)
  if (Math.abs(value) >= 1_000_000) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  }
  if (Math.abs(value) >= 1_000) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  }
  return formatCurrency(value)
}

export function formatDate(dateStr: string): string {
  // Handle both "YYYY-MM-DD" date strings and full ISO datetime strings
  const d = dateStr.includes('T') ? new Date(dateStr) : new Date(dateStr + 'T00:00:00')
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(d)
}

export function formatPct(value: number | string, decimals = 1): string {
  return `${Number(value).toFixed(decimals)}%`
}

import type { Key } from './i18n.tsx'

/** Client check of the report period (SPEC.md 9.6): both dates or neither, from ≤ to, at most 366 days inclusive. The API checks again. */
export function rangeError(from: string, to: string): Key | null {
  if (!from && !to) return null // the API's default: the current Asia/Kolkata month
  if (!from || !to) return 'rep.bothDates'
  const days = (Date.parse(to) - Date.parse(from)) / 86_400_000
  if (Number.isNaN(days)) return 'rep.bothDates'
  if (days < 0) return 'rep.order'
  return days > 365 ? 'rep.tooLong' : null
}

/** Parses rupees typed by a person ("450", "450.5", "1,250.75") into integer paise without floating point. null = not a valid amount. */
export function toPaise(text: string): number | null {
  const m = /^(\d{1,10})(?:\.(\d{1,2}))?$/.exec(text.trim().replaceAll(',', ''))
  if (!m) return null
  return Number(m[1]) * 100 + Number((m[2] ?? '').padEnd(2, '0'))
}

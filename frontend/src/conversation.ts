// Message paging helpers for the text conversation (SPEC.md 9.5 message history).
export const PAGE = 100

export type Message = { id: number; role: 'user' | 'assistant' | 'agent'; text: string; created_at: string }

/** Union by stable message id, oldest first: overlapping pages and repeated polls never duplicate or reorder. */
export function merge(a: Message[], b: Message[]): Message[] {
  const byId = new Map(a.map((m) => [m.id, m]))
  for (const m of b) byId.set(m.id, m)
  return [...byId.values()].sort((x, y) => x.id - y.id)
}

/** Every message newer than `after`: follows full pages until a short one, so nothing past message 500 is skipped. */
export async function newer(get: (after: number) => Promise<Message[]>, after: number): Promise<Message[]> {
  const all: Message[] = []
  for (;;) {
    const page = await get(after)
    all.push(...page)
    if (page.length < PAGE) return all
    after = page[page.length - 1].id
  }
}

type SupportChat = { id: string; created_at: string; support_case_id?: string | null; support_status?: 'queued' | 'assigned' | 'released' | null }
const RANK = { assigned: 0, queued: 1, released: 2 } as const

/**
 * The conversation a complaint should lead to (F06): one a support person is handling, then one waiting for support,
 * then one handed back; the newest first within each.
 */
export function supportChatFor<T extends SupportChat>(list: T[], caseId: string): T | undefined {
  return list
    .filter((c) => c.support_case_id === caseId && c.support_status)
    .sort((a, b) => RANK[a.support_status!] - RANK[b.support_status!] || b.created_at.localeCompare(a.created_at))[0]
}

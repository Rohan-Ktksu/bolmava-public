import assert from 'node:assert/strict'
import { test } from 'node:test'
import { merge, newer, PAGE, supportChatFor, type Message } from './conversation.ts'

const msg = (id: number): Message => ({ id, role: id % 2 ? 'user' : 'assistant', text: `m${id}`, created_at: '' })
const server = Array.from({ length: 523 }, (_, i) => msg(i + 1))
const after = async (id: number) => server.filter((m) => m.id > id).slice(0, PAGE)

test('polling forward reaches every message past 500 without gaps or duplicates', async () => {
  const got = await newer(after, 0)
  assert.deepEqual(got.map((m) => m.id), server.map((m) => m.id))
  assert.deepEqual(await newer(after, 523), [])
  assert.deepEqual((await newer(after, 500)).map((m) => m.id), [501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512, 513, 514, 515, 516, 517, 518, 519, 520, 521, 522, 523])
})

test('merging overlapping pages keeps one copy of each message in id order', () => {
  const newest = server.slice(-PAGE)
  const older = server.slice(-PAGE - 50, -PAGE + 10) // overlaps the newest page by 10
  const polled = [msg(523), msg(524)]
  const all = merge(merge(newest, older), polled)
  assert.equal(all.length, PAGE + 50 + 1)
  assert.deepEqual(all.map((m) => m.id), [...new Set(all.map((m) => m.id))].sort((a, b) => a - b))
  assert.equal(all.at(-1)!.id, 524)
})

test('a complaint leads to the chat support is handling, not a newer one still waiting (owner report, 22 November)', () => {
  const chat = (id: string, created_at: string, support_status: 'queued' | 'assigned' | 'released' | null, support_case_id: string | null = 'case') =>
    ({ id, created_at, support_status, support_case_id })
  const list = [
    chat('newest-waiting', '2026-11-22T07:08:00Z', 'queued'),
    chat('handled', '2026-11-22T07:00:00Z', 'assigned'),
    chat('other-complaint', '2026-11-22T07:09:00Z', 'assigned', 'other'),
    chat('plain', '2026-11-22T07:10:00Z', null, null),
  ]
  assert.equal(supportChatFor(list, 'case')?.id, 'handled')
  assert.equal(supportChatFor([chat('a', '2026-11-22T06:00:00Z', 'released'), chat('b', '2026-11-22T06:30:00Z', 'released')], 'case')?.id, 'b')
  assert.equal(supportChatFor([chat('w', '2026-11-22T06:00:00Z', 'queued'), chat('r', '2026-11-22T06:30:00Z', 'released')], 'case')?.id, 'w')
  assert.equal(supportChatFor(list, 'none'), undefined)
})

import { useEffect, useRef, useState } from 'react'
import { api, ApiError, post, type ConversationDetail, type ConversationSummary } from '../api.ts'
import { merge, newer, PAGE, type Message } from '../conversation.ts'
import { useDate, useLang, type Key } from '../i18n.tsx'
import { useSession } from '../session.tsx'
import { ErrorState, PageHead } from '../ui.tsx'
import { VoiceButton } from '../VoiceButton.tsx'
import { useSubmit } from './Trade.tsx'

const POLL_MS = 5000
const WHO: Record<Message['role'], Key> = { user: 'chat.role.user', assistant: 'wa.contact', agent: 'chat.role.agent' }

/**
 * A labelled stand-in for a WhatsApp chat (demo step 14). It is another client of the same conversation API: it opens
 * the person's latest conversation, so the history, support replies and records are the portal's. Nothing is sent to
 * WhatsApp or to any phone, and it never confirms anything.
 */
export function WhatsAppSim() {
  const { t } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const send = useSubmit()
  const base = `/orgs/${orgId}/conversations`
  const [convId, setConvId] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<Message[]>([])
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [text, setText] = useState('')
  const [fresh, setFresh] = useState(false) // "New chat": do not reopen the latest conversation
  // One key per typed message, reused on a retry, so a lost reply never stores the message twice.
  const sendKey = useRef<{ text: string; key: string } | null>(null)
  const last = useRef(0)

  const refresh = async (id: string) => {
    const got = last.current
      ? await newer((after) => api<Message[]>(`${base}/${id}/messages?after=${after}&limit=${PAGE}`), last.current)
      : await api<Message[]>(`${base}/${id}/messages?limit=${PAGE}`)
    const d = await api<ConversationDetail>(`${base}/${id}`)
    setMsgs((m) => {
      const next = merge(m, got)
      last.current = next.at(-1)?.id ?? 0
      return next
    })
    setDetail(d)
    setLoadError(null)
  }

  // Open the latest conversation (the same one the portal shows), unless the person started a new chat here.
  useEffect(() => {
    let alive = true
    setConvId(null)
    setMsgs([])
    setDetail(null)
    last.current = 0
    if (fresh) return
    api<ConversationSummary[]>(base).then(
      (list) => alive && setConvId(list[0]?.id ?? null),
      (e) => alive && setLoadError(e instanceof ApiError ? e : new ApiError(0, 'network', '')),
    )
    return () => void (alive = false)
  }, [base, fresh])

  // Keep the chat current: support replies arrive without the person sending anything.
  useEffect(() => {
    if (!convId) return
    let alive = true
    const tick = () => refresh(convId).catch((e) => alive && setLoadError(e instanceof ApiError ? e : new ApiError(0, 'network', '')))
    void tick()
    const timer = setInterval(tick, POLL_MS)
    return () => ((alive = false), clearInterval(timer))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh reads refs and the current base only
  }, [convId])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body = text.trim()
    if (!body || send.busy) return
    if (sendKey.current?.text !== body) sendKey.current = { text: body, key: crypto.randomUUID() }
    const key = sendKey.current.key
    void send.run(async () => {
      const id = convId ?? (await post<ConversationSummary>(base)).id
      if (!convId) setConvId(id)
      try {
        await post(`${base}/${id}/messages`, { text: body }, { 'Idempotency-Key': key })
        sendKey.current = null
        setText('')
      } finally {
        await refresh(id).catch(() => {}) // show what the server stored, sent or not
      }
    })
  }

  const handoff = detail?.handoff && detail.handoff.status !== 'released' ? detail.handoff : null
  return (
    <>
      <PageHead title={t('wa.title')} lead={t('wa.lead')} />
      <p className="callout" role="note">
        {t('wa.notReal')}
      </p>
      <div className="wa-phone">
        <div className="wa-head">
          <strong>{t('wa.contact')}</strong>
          <button type="button" className="btn ghost" onClick={() => (setFresh(true), setConvId(null), setMsgs([]), setDetail(null), (last.current = 0))}>
            {t('chat.new')}
          </button>
        </div>
        {loadError && <ErrorState error={loadError} onRetry={() => convId && void refresh(convId)} />}
        <ol className="wa-log" aria-label={t('wa.title')} tabIndex={0}>
          {msgs.length === 0 && <li className="note">{t('wa.empty')}</li>}
          {msgs.map((m) => (
            <li key={m.id} className={`wa-msg wa-${m.role}`}>
              <p>{m.text}</p>
              <small>
                {t(WHO[m.role])} · <time dateTime={m.created_at}>{date(m.created_at)}</time>
              </small>
            </li>
          ))}
        </ol>
        {handoff && <p className="note">{t(handoff.status === 'assigned' ? 'chat.handoff.assigned' : 'chat.handoff.queued')}</p>}
        {detail?.pending_action && <p className="note">{t('wa.confirmInApp')}</p>}
        <form className="composer" onSubmit={submit}>
          <label className="field">
            <span>{t('chat.message')}</span>
            <textarea rows={2} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <VoiceButton onText={(x) => setText((cur) => (cur ? `${cur} ${x}` : x))} />
          {send.error && <ErrorState error={send.error} />}
          <div className="form-actions">
            <button type="submit" className="btn primary" aria-disabled={send.busy}>
              {send.busy ? t('state.sending') : t('chat.send')}
            </button>
          </div>
        </form>
      </div>
    </>
  )
}

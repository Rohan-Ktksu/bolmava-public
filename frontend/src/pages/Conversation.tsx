import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import {
  api,
  ApiError,
  post,
  readEvents,
  useApi,
  type ConversationDetail,
  type ConversationSummary,
  type PendingAction,
  type PendingResult,
  type Product,
  type Quote,
} from '../api.ts'
import { merge, newer, PAGE, type Message } from '../conversation.ts'
import { VoiceButton } from '../VoiceButton.tsx'
import { productName, useDate, useLang, type Key } from '../i18n.tsx'
import { useSession } from '../session.tsx'
import { Empty, ErrorState, Loading, Money, PageHead } from '../ui.tsx'
import { Fact, Spec, Terms, useSubmit } from './Trade.tsx'

const POLL_MS = 5000 // without a live stream
const LIVE_POLL_EVERY = 6 // with one: a safety check every 30 s
const RECONNECT_MS = 3000

type Permission = NotificationPermission | 'unsupported'
const notifications = (): Permission => (typeof Notification === 'undefined' ? 'unsupported' : Notification.permission)

/** Text conversation with the deterministic assistant (SPEC.md 6.7). Private to the signed-in user. */
export function Conversation() {
  const { t } = useLang()
  const { orgId } = useSession()
  const navigate = useNavigate()
  const list = useApi<ConversationSummary[]>(orgId ? `/orgs/${orgId}/conversations` : null)
  const date = useDate()
  // The chosen conversation in this organization (null = a new one); `n` changes only on a choice, so creating
  // the new conversation on its first message does not remount the chat mid-send.
  // Another screen (a complaint) can name the conversation to open; otherwise the newest one opens.
  const opened = (useLocation().state as { open?: string } | null)?.open ?? null
  const [pick, setPick] = useState<{ org: string | null; id: string | null; n: number } | null>(opened ? { org: orgId, id: opened, n: 1 } : null)
  const isPicked = pick?.org === orgId
  const id = isPicked ? pick.id : list.data?.[0]?.id ?? null
  const n = isPicked ? pick.n : 0
  const choose = (next: string | null) => setPick({ org: orgId, id: next, n: n + 1 })
  const created = (next: string) => (setPick({ org: orgId, id: next, n }), list.retry())
  const known = list.data ?? []
  // Return to whatever the person was doing; a direct visit has nowhere to go back to.
  const back = () => ((window.history.state?.idx ?? 0) > 0 ? navigate(-1) : navigate('/'))
  return (
    <>
      <PageHead title={t('chat.title')} lead={t('chat.lead')}>
        <button type="button" className="back linklike" onClick={back}>
          ← {t('chat.back')}
        </button>
      </PageHead>
      {!orgId ? (
        <Empty title={t('chat.title')} text={t('chat.noOrg')} />
      ) : list.error && !list.data ? (
        <ErrorState error={list.error} onRetry={list.retry} />
      ) : !list.data ? (
        <Loading />
      ) : (
        <>
          <div className="chat-bar">
            {known.length > 0 && (
              <label className="field chat-pick">
                <span>{t('chat.pick')}</span>
                <select value={id ?? ''} onChange={(e) => choose(e.target.value || null)}>
                  {id === null && <option value="">{t('chat.newUnsent')}</option>}
                  {id !== null && !known.some((c) => c.id === id) && <option value={id}>{t('chat.current')}</option>}
                  {known.map((c, i) => (
                    <option key={c.id} value={c.id}>
                      {t(i === 0 ? 'chat.startedLatest' : 'chat.started', { date: date(c.created_at) })}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button type="button" className="btn ghost" onClick={() => choose(null)}>
              {t('chat.new')}
            </button>
          </div>
          <Chat key={`${orgId}:${n}`} initialId={id} onCreated={created} />
        </>
      )}
    </>
  )
}

function Chat({ initialId: chosenId, onCreated }: { initialId: string | null; onCreated: (id: string) => void }) {
  const { t, lang } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const [initialId] = useState(chosenId) // later prop changes (this chat's own creation) must not reload it
  const [convId, setConvId] = useState(initialId)
  const [unseen, setUnseen] = useState(false)
  const [perm, setPerm] = useState<Permission>(notifications)
  const sendKey = useRef<{ text: string; key: string } | null>(null)
  const [msgs, setMsgs] = useState<Message[]>([])
  const [hasOlder, setHasOlder] = useState(false)
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [loaded, setLoaded] = useState(initialId === null)
  const [attempt, setAttempt] = useState(0)
  const [olderError, setOlderError] = useState<ApiError | null>(null)
  const [olderBusy, setOlderBusy] = useState(false)
  const [text, setText] = useState('')
  const [announce, setAnnounce] = useState('')
  const [done, setDone] = useState<PendingResult | null>(null)
  const [pressed, setPressed] = useState<PendingAction | null>(null)
  const send = useSubmit()
  const human = useSubmit()

  const alive = useRef(true)
  useEffect(() => {
    alive.current = true // StrictMode mounts twice; the second mount must count as alive
    return () => void (alive.current = false)
  }, [])
  const lastId = useRef(0)
  const detailSeq = useRef(0)
  const base = `/orgs/${orgId}/conversations`

  // Scroll: keep the reader's place when older messages are added above; follow new ones only if already at the bottom.
  const log = useRef<HTMLOListElement>(null)
  const snap = useRef({ height: 0, top: 0, atBottom: true, first: 0 })
  const update = (fn: (m: Message[]) => Message[]) => {
    const el = log.current
    if (el) snap.current = { height: el.scrollHeight, top: el.scrollTop, atBottom: el.scrollHeight - el.scrollTop - el.clientHeight < 48, first: snap.current.first }
    setMsgs((m) => {
      const next = fn(m)
      lastId.current = next.at(-1)?.id ?? 0
      return next
    })
  }
  useLayoutEffect(() => {
    const el = log.current
    if (!el || msgs.length === 0) return
    const s = snap.current
    if (s.first && msgs[0].id < s.first) el.scrollTop = s.top + (el.scrollHeight - s.height)
    else if (s.atBottom) el.scrollTop = el.scrollHeight
    s.first = msgs[0].id
  }, [msgs])

  const loadDetail = useCallback(
    async (id: string) => {
      const seq = ++detailSeq.current
      const d = await api<ConversationDetail>(`${base}/${id}`)
      // Only the newest answer counts, so an older slow response cannot bring back a withdrawn proposal.
      if (alive.current && seq === detailSeq.current) setDetail(d)
    },
    [base],
  )
  const refresh = useCallback(
    async (id: string) => {
      const got = await newer((after) => api<Message[]>(`${base}/${id}/messages?after=${after}&limit=${PAGE}`), lastId.current)
      if (!alive.current) return
      if (got.length) {
        update((m) => merge(m, got))
        if (!snap.current.atBottom) setUnseen(true) // the reader scrolled up: offer a jump instead of moving them
        // Another tab or window has focus: a system notification, without message text (it may show on a lock screen).
        const replies = got.filter((m) => m.role !== 'user')
        if (replies.length && document.visibilityState === 'hidden' && notifications() === 'granted')
          new Notification('Bolmava', { body: t(replies.some((m) => m.role === 'agent') ? 'chat.notify.agent' : 'chat.notify.assistant'), tag: id })
      }
      await loadDetail(id)
    },
    [base, loadDetail, t],
  )

  // First load: the newest page and the conversation's live state.
  useEffect(() => {
    if (!initialId) return
    Promise.all([api<Message[]>(`${base}/${initialId}/messages?limit=${PAGE}`), loadDetail(initialId)]).then(
      ([page]) => {
        if (!alive.current) return
        update(() => page)
        setHasOlder(page.length === PAGE)
        setLoaded(true)
      },
      (e) => alive.current && setLoadError(e instanceof ApiError ? e : new ApiError(0, 'network', '')),
    )
  }, [initialId, base, loadDetail, attempt])

  // Newer messages arrive when the server pushes a change signal; a slow poll covers a dropped or reconnecting stream.
  useEffect(() => {
    if (!convId || !loaded) return
    const ctrl = new AbortController()
    let busy = false
    let again = false
    let live = false
    let ticks = 0
    // One refresh at a time; a signal that arrives meanwhile triggers exactly one more.
    const sync = () => {
      if (busy) return void (again = true)
      busy = true
      refresh(convId)
        .catch(() => {}) // a missed refresh is repeated by the next signal or poll
        .finally(() => {
          busy = false
          if (again) {
            again = false
            sync()
          }
        })
    }
    void (async () => {
      while (!ctrl.signal.aborted) {
        try {
          // `ready` also syncs, catching anything committed before the subscription started.
          await readEvents(`${base}/${convId}/events`, ctrl.signal, () => ((live = true), sync()))
        } catch {
          if (!ctrl.signal.aborted) await new Promise((r) => setTimeout(r, RECONNECT_MS))
        }
        live = false // the server ends each stream after a few minutes; reconnecting re-checks the token
      }
    })()
    const poll = () => document.visibilityState === 'visible' && sync()
    const timer = setInterval(() => (!live || ++ticks % LIVE_POLL_EVERY === 0) && poll(), POLL_MS)
    document.addEventListener('visibilitychange', poll) // catch up at once when the person comes back to the tab
    return () => (ctrl.abort(), clearInterval(timer), document.removeEventListener('visibilitychange', poll))
  }, [convId, loaded, base, refresh])

  const loadOlder = async () => {
    if (!convId || olderBusy || msgs.length === 0) return
    setOlderBusy(true)
    setOlderError(null)
    try {
      const page = await api<Message[]>(`${base}/${convId}/messages?before=${msgs[0].id}&limit=${PAGE}`)
      if (!alive.current) return
      update((m) => merge(page, m))
      setHasOlder(page.length === PAGE)
    } catch (e) {
      if (alive.current) setOlderError(e instanceof ApiError ? e : new ApiError(0, 'network', ''))
    } finally {
      if (alive.current) setOlderBusy(false)
    }
  }

  const ensureConversation = async () => {
    if (convId) return convId
    const c = await post<ConversationSummary>(base)
    if (alive.current) {
      setConvId(c.id)
      onCreated(c.id)
    }
    return c.id
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body = text.trim()
    if (!body || send.busy) return
    // One key per composed message, reused when the same text is retried, so a lost response never stores it twice.
    if (sendKey.current?.text !== body) sendKey.current = { text: body, key: crypto.randomUUID() }
    const key = sendKey.current.key
    send.run(async () => {
      const id = await ensureConversation()
      try {
        const r = await post<{ reply: string }>(`${base}/${id}/messages`, { text: body }, { 'Idempotency-Key': key })
        if (!alive.current) return
        sendKey.current = null
        setText('')
        setDone(null)
        setPressed(null) // a new message withdraws any earlier proposal on the server too
        setAnnounce(r.reply)
      } finally {
        // Sent or not, show what the server actually stored before the person tries again.
        await refresh(id).catch(() => {})
      }
    })
  }

  const askPerson = () =>
    human.run(async () => {
      const id = await ensureConversation()
      await post(`${base}/${id}/handoff`, {})
      await refresh(id)
    })

  if (loadError) return <ErrorState error={loadError} onRetry={() => (setLoadError(null), setAttempt((n) => n + 1))} />
  if (!loaded) return <Loading />

  const handoff = detail?.handoff ?? null
  // A proposal the person pressed Confirm on stays until its outcome is shown, even if the server's live update
  // already removed it (for example a confirm whose response was lost: pressing again returns the same result).
  const pending = (handoff ? null : detail?.pending_action) ?? pressed
  const replyLang = detail?.language ?? lang
  return (
    <div className="chat">
      <p className="note">{t('chat.replyLang', { lang: replyLang === 'te' ? 'తెలుగు' : 'English' })}</p>
      {perm === 'default' ? (
        <div>
          <button type="button" className="btn ghost" onClick={() => void Notification.requestPermission().then(setPerm)}>
            {t('chat.notify.enable')}
          </button>
        </div>
      ) : (
        perm !== 'unsupported' && <p className="note">{t(perm === 'granted' ? 'chat.notify.on' : 'chat.notify.blocked')}</p>
      )}

      {hasOlder && (
        <div className="chat-older">
          <button type="button" className="btn" onClick={loadOlder} aria-disabled={olderBusy}>
            {olderBusy ? t('state.loading') : t('chat.older')}
          </button>
        </div>
      )}
      {olderError && <ErrorState error={olderError} onRetry={loadOlder} />}
      {msgs.length === 0 ? (
        <Empty title={t('chat.emptyTitle')} text={t('chat.empty')} />
      ) : (
        // Focusable so keyboard users can scroll the history; replies are announced separately below.
        <ol
          className="chat-log"
          ref={log}
          tabIndex={0}
          aria-label={t('chat.messages')}
          onScroll={(e) => unseen && e.currentTarget.scrollHeight - e.currentTarget.scrollTop - e.currentTarget.clientHeight < 48 && setUnseen(false)}
        >
          {msgs.map((m) => (
            <li key={m.id} className={`msg msg-${m.role}`}>
              <span className="msg-who">
                {t(`chat.role.${m.role}` as Key)} · <time dateTime={m.created_at}>{date(m.created_at)}</time>
              </span>
              <p>{m.text}</p>
            </li>
          ))}
        </ol>
      )}
      <p className="visually-hidden" role="status">
        {announce}
      </p>

      {unseen && (
        <div className="chat-older">
          <button
            type="button"
            className="btn primary"
            onClick={() => {
              log.current?.scrollTo({ top: log.current.scrollHeight })
              setUnseen(false)
            }}
          >
            {t('chat.newBelow')}
          </button>
        </div>
      )}
      {handoff && (
        <section className="callout" role="status" aria-labelledby="handoff-title">
          <h2 id="handoff-title">{t('chat.handoff.title')}</h2>
          <p>{t(handoff.status === 'assigned' ? 'chat.handoff.assigned' : 'chat.handoff.queued')}</p>
        </section>
      )}
      {done && <Done result={done} />}
      {pending && (
        <Proposal
          key={pending.id}
          pa={pending}
          onPress={() => setPressed(pending)}
          onDone={(r) => (setPressed(null), setDone(r), convId && refresh(convId).catch(() => {}))}
          onStale={() => convId && refresh(convId).catch(() => {})}
        />
      )}

      <form className="composer" onSubmit={submit}>
        <label className="field">
          <span>{t('chat.message')}</span>
          <textarea
            rows={2}
            maxLength={1000}
            value={text}
            aria-describedby="chat-hint"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) submit(e)
            }}
          />
          <small id="chat-hint">{t(handoff ? 'chat.hintPaused' : 'chat.hint')}</small>
        </label>
        <VoiceButton onText={(x) => setText((cur) => (cur ? `${cur} ${x}` : x))} />
        {send.error && (
          <>
            <ErrorState error={send.error} />
            {send.error.code === 'network' && <p className="note">{t('chat.maybeSent')}</p>}
          </>
        )}
        <div className="form-actions">
          <button type="submit" className="btn primary" aria-disabled={send.busy}>
            {send.busy ? t('state.sending') : t('chat.send')}
          </button>
          {!handoff && (
            <button type="button" className="btn" onClick={askPerson} aria-disabled={human.busy}>
              {human.busy ? t('state.sending') : t('chat.askPerson')}
            </button>
          )}
        </div>
        {!handoff && <p className="note">{t('chat.askPersonNote')}</p>}
        {human.error && <ErrorState error={human.error} />}
      </form>
    </div>
  )
}

/** A proposal from the assistant. Nothing happens until the separate Confirm press; the API re-checks everything. */
function Proposal({ pa, onPress, onDone, onStale }: { pa: PendingAction; onPress: () => void; onDone: (r: PendingResult) => void; onStale: () => void }) {
  const { t, lang } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const submit = useSubmit()
  const [expired, setExpired] = useState(() => Date.parse(pa.expires_at) <= Date.now())
  const [gone, setGone] = useState<Key | null>(null)
  useEffect(() => {
    const ms = Date.parse(pa.expires_at) - Date.now()
    if (ms <= 0) return
    const timer = setTimeout(() => setExpired(true), Math.min(ms, 2 ** 31 - 1))
    return () => clearTimeout(timer)
  }, [pa.expires_at])

  const isOrder = pa.action === 'confirm_order'
  const quote = useApi<Quote>(isOrder ? `/orgs/${orgId}/quotes/${pa.payload.quote_id}` : null)
  const product = useApi<Product>(isOrder ? null : `/catalog/products/${pa.payload.product_id}`)
  const terms = isOrder ? quote : product
  // The quote must still be the exact one proposed; otherwise the API would refuse it, so do not offer Confirm.
  const q = quote.data
  const changed = isOrder && !!q && (q.version !== pa.payload.quote_version || q.total_paise !== pa.payload.total_paise || q.status !== 'sent')
  const blocked = gone ?? (expired ? 'chat.pa.expired' : changed ? 'chat.pa.changed' : null)

  const confirm = () =>
    submit.run(async () => {
      onPress()
      try {
        onDone(await post<PendingResult>(`/orgs/${orgId}/pending-actions/${pa.id}/confirm`))
      } catch (e) {
        if (e instanceof ApiError && e.code === 'pending_action_not_active') {
          setGone(e.details?.status === 'cancelled' ? 'chat.pa.cancelled' : 'chat.pa.expired')
          return onStale()
        }
        if (e instanceof ApiError && e.code === 'conversation_paused') {
          setGone('chat.pa.paused')
          return onStale()
        }
        throw e // stock, quote and permission errors: show the API's own message; pressing again is safe
      }
    })

  return (
    <section className="review proposal" aria-labelledby="pa-title">
      <h2 id="pa-title">{t(isOrder ? 'chat.pa.orderTitle' : 'chat.pa.rfqTitle')}</h2>
      <p>{t(isOrder ? 'chat.pa.orderLead' : 'chat.pa.rfqLead')}</p>
      {terms.error && <ErrorState error={terms.error} onRetry={terms.retry} />}
      {terms.loading && <Loading />}
      {isOrder && q && (
        <>
          <Spec s={q.product_snapshot} />
          <dl className="facts">
            <Fact label={t('confirm.version')} value={String(pa.payload.quote_version)} />
            <Fact label={t('chat.pa.validUntil')} value={date(q.valid_until)} />
          </dl>
          <Terms money={q} unit={t(`unit.${q.product_snapshot.unit}`)} />
          <p className="note">{t('confirm.simulated')}</p>
        </>
      )}
      {!isOrder && product.data && (
        <dl className="facts">
          <Fact label={t('terms.product')} value={productName(lang, product.data)} />
          <Fact label={t('product.seller')} value={product.data.seller.name} />
          <Fact label={t('chat.pa.quantity')} value={`${pa.payload.quantity} × ${t(`unit.${product.data.unit}`)}`} />
          <Fact label={t('chat.pa.city')} value={pa.payload.delivery_city} />
        </dl>
      )}
      <p className="note">{t('chat.pa.expires', { time: date(pa.expires_at) })}</p>
      {blocked ? (
        <p className="flash" role="status">
          {t(blocked)}
        </p>
      ) : (
        terms.data && (
          <div className="form-actions">
            <button type="button" className="btn primary" onClick={confirm} aria-disabled={submit.busy}>
              {submit.busy ? t('state.sending') : t(isOrder ? 'chat.pa.confirmOrder' : 'chat.pa.confirmRfq')}
            </button>
          </div>
        )
      )}
      {submit.error && <ErrorState error={submit.error} />}
    </section>
  )
}

function Done({ result }: { result: PendingResult }) {
  const { t } = useLang()
  return (
    <p className="flash" role="status">
      {result.action === 'create_rfq' ? (
        <>
          {t('chat.done.rfq', { org: result.rfq.seller_org_name })} <Link to={`/requests/${result.rfq.id}`}>{t('chat.done.openRfq')}</Link>
        </>
      ) : (
        <>
          {t('chat.done.order')} <Money paise={result.order.total_paise} />. <Link to={`/orders/${result.order.id}`}>{t('chat.done.openOrder')}</Link>
        </>
      )}
    </p>
  )
}

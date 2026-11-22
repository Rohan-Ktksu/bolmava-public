import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError, post, useApi, type CaseDetail, type HandoffSummary, type QueueItem, type StaffHandoff, type Case } from '../api.ts'
import { useDate, useLang, type Key } from '../i18n.tsx'
import { useSession } from '../session.tsx'
import { Empty, ErrorState, Loading, PageHead } from '../ui.tsx'
import { Fact, Status, useSubmit } from './Trade.tsx'

/** Support workspace (SPEC.md 9.2, 9.5). The API decides who may see what; these screens never widen it. */
const POLL_MS = 5000
const ref = (id: string) => id.slice(0, 8)
type Kind = 'cases' | 'handoffs'
type List<T> = { data?: T[]; error?: ApiError; retry: () => void }

function Rows<T>({ q, empty, row }: { q: List<T>; empty: Key; row: (x: T) => ReactNode }) {
  const { t } = useLang()
  if (q.error) return <ErrorState error={q.error} onRetry={q.retry} />
  if (!q.data) return <Loading />
  if (!q.data.length) return <p className="note">{t(empty)}</p>
  return <ul className="rows">{q.data.map(row)}</ul>
}

const Back = () => <Link to="/support">← {useLang().t('sup.back')}</Link>

export function SupportQueue() {
  const { t } = useLang()
  const location = useLocation()
  const [flash, setFlash] = useState<Key | null>((location.state as { flash?: Key } | null)?.flash ?? null)
  return (
    <>
      <PageHead title={t('nav.support')} lead={t('sup.lead')} />
      {flash && (
        <p className="flash" role="status">
          {t(flash)}
        </p>
      )}
      <Queue kind="cases" onFlash={setFlash} />
      <Queue kind="handoffs" onFlash={setFlash} />
    </>
  )
}

function Queue({ kind, onFlash }: { kind: Kind; onFlash: (k: Key) => void }) {
  const { t } = useLang()
  const date = useDate()
  const navigate = useNavigate()
  const waiting = useApi<QueueItem[]>(`/staff/${kind}?scope=unassigned`)
  const mine = useApi<(Case | StaffHandoff)[]>(`/staff/${kind}?scope=mine`)
  const take = useSubmit()
  const [taking, setTaking] = useState('')
  const title = (x: QueueItem | Case | StaffHandoff) => ('category' in x && x.category ? t(`case.cat.${x.category}`) : t('sup.ho.row'))

  const takeOne = (id: string) => {
    setTaking(id)
    void take.run(async () => {
      try {
        await post(`/staff/${kind}/${id}/take`)
        navigate(`/support/${kind}/${id}`)
      } catch (e) {
        // Another person took it between loading the list and pressing Take.
        if (e instanceof ApiError && e.code === 'invalid_transition') return onFlash('sup.taken'), waiting.retry()
        throw e
      }
    })
  }

  return (
    <section className="support-section" aria-labelledby={`q-${kind}`}>
      <h2 id={`q-${kind}`}>{t(kind === 'cases' ? 'sup.cases' : 'sup.handoffs')}</h2>
      <h3>{t('sup.waiting')}</h3>
      <Rows
        q={waiting}
        empty="sup.emptyWaiting"
        row={(x) => (
          <li key={x.id} className="row-card">
            <span className="row-main">
              <strong>{title(x)}</strong>
              <span>
                {t('sup.urgency')}: {t(`urgency.${x.urgency}`)}
              </span>
              <small>
                {t('sup.ref', { ref: ref(x.id) })} · {date(x.created_at)}
              </small>
              {x.your_case_id && <span className="status status-assigned">{t('sup.ho.yourCase', { ref: ref(x.your_case_id) })}</span>}
            </span>
            <button type="button" className="btn primary" onClick={() => takeOne(x.id)} aria-disabled={take.busy}>
              {take.busy && taking === x.id ? t('state.sending') : t('sup.take')}
            </button>
          </li>
        )}
      />
      {take.error && <ErrorState error={take.error} />}
      <h3>{t('sup.mine')}</h3>
      <Rows
        q={mine}
        empty="sup.emptyMine"
        row={(x) => {
          const body = (
            <>
              <span className="row-main">
                <strong>{title(x)}</strong>
                <small>
                  {t('sup.ref', { ref: ref(x.id) })} · {date(x.created_at)}
                </small>
              </span>
              <Status kind={kind === 'cases' ? 'case' : 'handoff'} value={x.status} />
            </>
          )
          // A handed-back conversation keeps only this row: its messages are no longer available (SPEC.md 9.5).
          return (
            <li key={x.id}>
              {x.status === 'released' ? (
                <div className="row-card">{body}</div>
              ) : (
                <Link to={`/support/${kind}/${x.id}`} className="row-card">
                  {body}
                </Link>
              )}
            </li>
          )
        }}
      />
    </section>
  )
}

/** Shown for 404: not assigned to this person (or not there). The API reveals nothing more, and neither do we. */
function NotYours() {
  const { t } = useLang()
  return (
    <>
      <Back />
      <Empty title={t('sup.notYours')} text={t('sup.notYoursText')} />
    </>
  )
}

export function SupportCase() {
  const { id = '' } = useParams()
  const { t } = useLang()
  const { me } = useSession()
  const date = useDate()
  const c = useApi<CaseDetail>(`/staff/cases/${id}`)
  const act = useSubmit()
  // The customer's chat about this complaint, when this person handles it (newest first): one screen for both.
  const mine = useApi<StaffHandoff[]>('/staff/handoffs?scope=mine')
  const linked = mine.data?.find((h) => h.status === 'assigned' && h.case_id === id)
  const chat = useHandoff(linked?.id ?? null)
  // A chat about this complaint still waiting in the shared queue: anyone may take it, but this page offers it first.
  const queue = useApi<QueueItem[]>('/staff/handoffs?scope=unassigned')
  const waiting = linked ? undefined : queue.data?.find((x) => x.your_case_id === id)
  const takeChat = useSubmit()
  const [chatFlash, setChatFlash] = useState<Key | null>(null)
  const { retry: findChats } = mine
  const { retry: findWaiting } = queue
  useEffect(() => {
    const timer = setInterval(() => (findChats(), findWaiting()), POLL_MS) // chats started later appear without reloading
    return () => clearInterval(timer)
  }, [findChats, findWaiting])
  const [flash, setFlash] = useState<Key | null>(null)
  const [text, setText] = useState('')
  const [resolution, setResolution] = useState('')
  const [missing, setMissing] = useState<'text' | 'resolution' | null>(null)

  if (c.error) return c.error.status === 404 ? <NotYours /> : <ErrorState error={c.error} onRetry={c.retry} />
  if (!c.data) return <Loading />
  const d = c.data

  const run = (path: string, body: object, after: () => void) =>
    act.run(async () => {
      setFlash(null)
      try {
        await post(`/staff/cases/${id}/${path}`, body)
        after()
      } catch (e) {
        // The case moved on (for example the buyer closed it): show its current state instead.
        if (e instanceof ApiError && e.code === 'invalid_transition') return setFlash('sup.case.changed'), c.retry()
        throw e
      }
      c.retry()
    })
  const write = (visibility: 'parties' | 'internal') => {
    if (!text.trim()) return setMissing('text')
    setMissing(null)
    void run('updates', { body: text.trim(), visibility }, () => setText(''))
  }
  const resolve = (e: React.FormEvent) => {
    e.preventDefault()
    if (!resolution.trim()) return setMissing('resolution')
    setMissing(null)
    void run('resolve', { resolution: resolution.trim() }, () => setResolution(''))
  }
  const updates = (visibility: 'parties' | 'internal') => d.updates.filter((u) => u.visibility === visibility)
  const open = d.status !== 'closed'

  return (
    <>
      <PageHead title={t('sup.case.title', { ref: ref(d.id) })}>
        <Back />
      </PageHead>
      {flash && (
        <p className="flash" role="status">
          {t(flash)}
        </p>
      )}
      <dl className="facts">
        <Fact label={t('sup.case.category')} value={t(`case.cat.${d.category}`)} />
        <Fact label={t('sup.urgency')} value={t(`urgency.${d.urgency}`)} />
        <Fact label={t('sup.case.status')} value={<Status kind="case" value={d.status} />} />
        <Fact label={t('sup.case.order')} value={ref(d.order_id)} />
        <Fact label={t('sup.case.opened')} value={date(d.created_at)} />
        {d.reopen_count > 0 && <Fact label={t('sup.case.reopened')} value={String(d.reopen_count)} />}
      </dl>
      <h2>{t('sup.case.description')}</h2>
      <p>{d.description}</p>
      {d.resolution && (
        <>
          <h2>{t('sup.case.resolution')}</h2>
          <p>{d.resolution}</p>
        </>
      )}

      {chatFlash && (
        <p className="flash" role="status">
          {t(chatFlash)}
        </p>
      )}
      {waiting && (
        <section className="callout" role="status" aria-labelledby="waiting-chat">
          <h2 id="waiting-chat">{t('sup.case.waitingChat')}</h2>
          {takeChat.error && <ErrorState error={takeChat.error} />}
          <div className="form-actions">
            <button
              type="button"
              className="btn primary"
              aria-disabled={takeChat.busy}
              onClick={() =>
                takeChat.run(async () => {
                  setChatFlash(null)
                  try {
                    await post(`/staff/handoffs/${waiting.id}/take`)
                  } catch (e) {
                    // Someone else took it first; the queue shows who has what.
                    if (!(e instanceof ApiError && e.code === 'invalid_transition')) throw e
                    setChatFlash('sup.taken')
                  }
                  findChats()
                  findWaiting()
                })
              }
            >
              {takeChat.busy ? t('state.sending') : t('sup.case.takeChat')}
            </button>
          </div>
        </section>
      )}
      {linked && chat.released && (
        <p className="callout" role="status">
          {t('sup.ho.released')}
        </p>
      )}
      {linked && !chat.released && chat.data && (
        <section className="support-section case-chat" aria-labelledby="case-chat-title">
          <h2 id="case-chat-title">{t('sup.case.chat', { name: chat.data.requester_name })}</h2>
          <p className="note">{t('sup.case.chatNote', { name: chat.data.requester_name })}</p>
          <HandoffChat id={linked.id} s={chat.data} refresh={chat.retry} onReleased={() => (chat.setReleased(), findChats())} />
        </section>
      )}

      <section className="support-section" aria-labelledby="parties-title">
        <h2 id="parties-title">{t('sup.case.parties')}</h2>
        <p className="note">{t('sup.case.partiesNote')}</p>
        <Updates list={updates('parties')} me={me!.id} />
      </section>
      <section className="support-section internal" aria-labelledby="internal-title">
        <h2 id="internal-title">{t('sup.case.internal')}</h2>
        <p className="note">{t('sup.case.internalNote')}</p>
        <Updates list={updates('internal')} me={me!.id} />
      </section>

      <section className="support-section" aria-labelledby="evidence-title">
        <h2 id="evidence-title">{t('sup.case.evidence')}</h2>
        <p className="note">{t('sup.case.evidenceNote')}</p>
        {d.evidence.length === 0 ? (
          <p className="note">{t('sup.case.none')}</p>
        ) : (
          <ul className="rows">
            {d.evidence.map((e) => (
              <li key={e.id} className="row-card">
                <span className="row-main">
                  <strong>{e.filename}</strong>
                  <span>
                    {e.content_type} · {t('sup.case.bytes', { n: e.size_bytes })}
                  </span>
                  {e.description && <span>{e.description}</span>}
                  <small>
                    SHA-256 {e.sha256.slice(0, 16)}… · {date(e.created_at)}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {open && (
        <section className="support-section" aria-labelledby="write-title">
          <h2 id="write-title">{t('sup.case.write')}</h2>
          <label className="field">
            <span>{t('sup.case.writeLabel')}</span>
            <textarea
              rows={3}
              maxLength={2000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-invalid={missing === 'text'}
              aria-describedby={missing === 'text' ? 'write-err' : undefined}
            />
            {missing === 'text' && (
              <small id="write-err" className="field-error" role="alert">
                {t('sup.case.needText')}
              </small>
            )}
          </label>
          <div className="form-actions">
            <button type="button" className="btn primary" onClick={() => write('parties')} aria-disabled={act.busy}>
              {t('sup.case.sendParties')}
            </button>
            <button type="button" className="btn" onClick={() => write('internal')} aria-disabled={act.busy}>
              {t('sup.case.saveInternal')}
            </button>
          </div>
        </section>
      )}

      {(d.status === 'assigned' || d.status === 'investigating') && (
        <section className="support-section" aria-labelledby="status-title">
          <h2 id="status-title">{t('sup.case.progress')}</h2>
          {d.status === 'assigned' && (
            <div className="form-actions">
              <button type="button" className="btn" onClick={() => void run('investigate', {}, () => {})} aria-disabled={act.busy}>
                {t('sup.case.investigate')}
              </button>
            </div>
          )}
          <form onSubmit={resolve} noValidate>
            <label className="field">
              <span>{t('sup.case.resolveLabel')}</span>
              <textarea
                rows={3}
                maxLength={2000}
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
                aria-invalid={missing === 'resolution'}
                aria-describedby={missing === 'resolution' ? 'resolve-err' : 'resolve-note'}
              />
              {missing === 'resolution' && (
                <small id="resolve-err" className="field-error" role="alert">
                  {t('sup.case.needResolution')}
                </small>
              )}
              <small id="resolve-note">{t('sup.case.noMoney')}</small>
            </label>
            <div className="form-actions">
              <button type="submit" className="btn primary" aria-disabled={act.busy}>
                {t('sup.case.resolve')}
              </button>
            </div>
          </form>
        </section>
      )}
      {act.error && <ErrorState error={act.error} />}
    </>
  )
}

function Updates({ list, me }: { list: CaseDetail['updates']; me: string }) {
  const { t } = useLang()
  const date = useDate()
  if (!list.length) return <p className="note">{t('sup.case.none')}</p>
  return (
    <ol className="rows">
      {list.map((u) => (
        <li key={u.id} className="msg">
          <span className="msg-who">
            {t(u.author_id === me ? 'sup.case.byYou' : 'sup.case.byParty')} · <time dateTime={u.created_at}>{date(u.created_at)}</time>
          </span>
          <p>{u.body}</p>
        </li>
      ))}
    </ol>
  )
}

/** A handoff summary kept current by polling; after release it stops asking (SPEC.md 9.5, R03). */
function useHandoff(id: string | null) {
  const [releasedId, setReleasedId] = useState<string | null>(null) // per handoff, so a newer chat still loads
  const released = !!id && releasedId === id
  const h = useApi<HandoffSummary>(id && !released ? `/staff/handoffs/${id}` : null)
  const live = !!h.data
  const { retry } = h
  useEffect(() => {
    if (!live) return
    const timer = setInterval(retry, POLL_MS)
    return () => clearInterval(timer)
  }, [live, retry])
  return { ...h, released, setReleased: () => setReleasedId(id) }
}

/** The customer's recent messages, a reply box and hand back: shared by the conversation page and the complaint page. */
function HandoffChat({ id, s, refresh, onReleased }: { id: string; s: HandoffSummary; refresh: () => void; onReleased: () => void }) {
  const { t } = useLang()
  const date = useDate()
  const reply = useSubmit()
  const release = useSubmit()
  const [text, setText] = useState('')
  const [asking, setAsking] = useState(false)
  const send = (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    void reply.run(async () => {
      await post(`/staff/handoffs/${id}/messages`, { text: text.trim() })
      setText('')
      refresh()
    })
  }
  const handBack = () =>
    release.run(async () => {
      await post(`/staff/handoffs/${id}/release`)
      onReleased()
    })
  return (
    <>
      <h3>{t('sup.ho.recent')}</h3>
      <ol className="chat-log" tabIndex={0} aria-label={t('sup.ho.recent')}>
        {s.recent_messages.map((m) => (
          <li key={m.id} className={`msg msg-${m.role}`}>
            <span className="msg-who">
              {m.role === 'user' ? s.requester_name : t(m.role === 'agent' ? 'sup.ho.you' : 'chat.role.assistant')} ·{' '}
              <time dateTime={m.created_at}>{date(m.created_at)}</time>
            </span>
            <p>{m.text}</p>
          </li>
        ))}
      </ol>
      <form className="composer" onSubmit={send}>
        <label className="field">
          <span>{t('sup.ho.reply')}</span>
          <textarea rows={2} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        {reply.error && <ErrorState error={reply.error} />}
        <div className="form-actions">
          <button type="submit" className="btn primary" aria-disabled={reply.busy}>
            {reply.busy ? t('state.sending') : t('sup.ho.send')}
          </button>
        </div>
      </form>
      {asking ? (
        <div className="confirm-box" role="group" aria-labelledby={`release-ask-${id}`}>
          <p id={`release-ask-${id}`}>{t('sup.ho.releaseAsk')}</p>
          {release.error && <ErrorState error={release.error} />}
          <div className="form-actions">
            <button type="button" className="btn danger" onClick={handBack} aria-disabled={release.busy}>
              {release.busy ? t('state.sending') : t('sup.ho.releaseYes')}
            </button>
            <button type="button" className="btn ghost" onClick={() => setAsking(false)} aria-disabled={release.busy}>
              {t('sup.ho.keep')}
            </button>
          </div>
        </div>
      ) : (
        <div className="form-actions">
          <button type="button" className="btn" onClick={() => setAsking(true)}>
            {t('sup.ho.release')}
          </button>
        </div>
      )}
    </>
  )
}

export function SupportHandoff() {
  const { id = '' } = useParams()
  const { t } = useLang()
  const { me } = useSession()
  const h = useHandoff(id)

  if (h.released)
    return (
      <>
        <Back />
        <section className="callout" role="status">
          <p>{t('sup.ho.released')}</p>
        </section>
      </>
    )
  if (h.error) return h.error.status === 404 ? <NotYours /> : <ErrorState error={h.error} onRetry={h.retry} />
  if (!h.data) return <Loading />
  const s = h.data

  return (
    <>
      <PageHead title={t('sup.ho.title', { name: s.requester_name })}>
        <Back />
      </PageHead>
      <p className="callout">{t('sup.ho.paused')}</p>
      <dl className="facts">
        <Fact label={t('sup.ho.org')} value={s.organization_name} />
        <Fact label={t('sup.ho.language')} value={s.language === 'te' ? 'తెలుగు' : 'English'} />
        <Fact label={t('sup.urgency')} value={t(`urgency.${s.urgency}`)} />
        {s.case && (
          <Fact
            label={t('sup.ho.case')}
            value={
              <>
                {s.case.assigned_to === me!.id ? <Link to={`/support/cases/${s.case.id}`}>{ref(s.case.id)}</Link> : ref(s.case.id)}{' '}
                <Status kind="case" value={s.case.status} />
              </>
            }
          />
        )}
        {s.order_status && <Fact label={t('sup.ho.orderStatus')} value={<Status kind="order" value={s.order_status} />} />}
      </dl>
      {s.cancelled_actions.length > 0 && (
        <>
          <h2>{t('sup.ho.cancelled')}</h2>
          <ul>
            {s.cancelled_actions.map((a, i) => (
              <li key={i}>{t(`sup.action.${a}`)}</li>
            ))}
          </ul>
        </>
      )}
      <section className="support-section" aria-label={t('sup.ho.recent')}>
        <HandoffChat id={id} s={s} refresh={h.retry} onReleased={h.setReleased} />
      </section>
    </>
  )
}

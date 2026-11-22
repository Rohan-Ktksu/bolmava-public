import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError, post, useApi, type Case, type CaseCategory, type CaseDetail, type ConversationDetail, type ConversationSummary, type Order } from '../api.ts'
import { supportChatFor } from '../conversation.ts'
import { fileDetails } from '../evidence.ts'
import { useDate, useLang, type Key } from '../i18n.tsx'
import { can } from '../nav.ts'
import { useSession } from '../session.tsx'
import { Empty, ErrorState, Loading, PageHead } from '../ui.tsx'
import { Fact, Status, useSubmit } from './Trade.tsx'

/** Complaints for the buyer and seller of an order (SPEC.md 9.2, 9.5). Party messages only: internal notes never reach this screen. */
const CATEGORIES: CaseCategory[] = ['damaged', 'wrong_product', 'missing_quantity', 'delay', 'quality', 'payment', 'other']
const MAX_BYTES = 20 * 1024 * 1024
const ref = (id: string) => id.slice(0, 8)

export function Complaints() {
  const { t } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const list = useApi<Case[]>(`/orgs/${orgId}/cases`)
  return (
    <>
      <PageHead title={t('nav.complaints')} lead={t('cmp.lead')} />
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.retry} />
      ) : !list.data ? (
        <Loading />
      ) : list.data.length === 0 ? (
        <Empty title={t('cmp.emptyTitle')} text={t('cmp.empty')} />
      ) : (
        <ul className="rows">
          {list.data.map((c) => (
            <li key={c.id}>
              <Link to={`/complaints/${c.id}`} className="row-card">
                <span className="row-main">
                  <strong>{t(`case.cat.${c.category}`)}</strong>
                  <span>{t(c.buyer_org_id === orgId ? 'cmp.yours' : 'cmp.aboutYou')}</span>
                  <small>
                    {t('fin.order', { ref: ref(c.order_id) })} · {date(c.created_at)}
                  </small>
                </span>
                <Status kind="case" value={c.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** On an order: the buyer's admin or purchaser can open a complaint. */
export function OpenComplaint({ order }: { order: Order }) {
  const { t } = useLang()
  const { me, orgId } = useSession()
  const navigate = useNavigate()
  const submit = useSubmit()
  const [open, setOpen] = useState(false)
  const [missing, setMissing] = useState(false)
  if (order.buyer_org_id !== orgId || !can(me!, orgId, 'buy')) return null
  if (!open)
    return (
      <div className="form-actions">
        <button type="button" className="btn" onClick={() => setOpen(true)}>
          {t('cmp.open')}
        </button>
      </div>
    )
  const send = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const description = String(f.get('description') ?? '').trim()
    if (!description) return setMissing(true)
    setMissing(false)
    void submit.run(async () => {
      const c = await post<Case>(`/orgs/${orgId}/orders/${order.id}/cases`, { category: f.get('category'), urgency: f.get('urgency'), description })
      navigate(`/complaints/${c.id}`, { state: { flash: 'cmp.opened' } })
    })
  }
  return (
    <form className="quote-form" onSubmit={send} noValidate aria-labelledby="cmp-open-title">
      <h2 id="cmp-open-title">{t('cmp.open')}</h2>
      <p className="note">{t('cmp.openLead')}</p>
      <label className="field">
        <span>{t('sup.case.category')}</span>
        <select name="category" defaultValue="damaged">
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`case.cat.${c}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('sup.urgency')}</span>
        <select name="urgency" defaultValue="normal">
          {(['low', 'normal', 'high'] as const).map((u) => (
            <option key={u} value={u}>
              {t(`urgency.${u}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('cmp.what')}</span>
        <textarea name="description" rows={3} maxLength={2000} aria-invalid={missing} aria-describedby={missing ? 'cmp-err' : undefined} />
        {missing && (
          <small id="cmp-err" className="field-error" role="alert">
            {t('cmp.needWhat')}
          </small>
        )}
      </label>
      {submit.error && <ErrorState error={submit.error} />}
      <div className="form-actions">
        <button type="submit" className="btn primary" aria-disabled={submit.busy}>
          {submit.busy ? t('state.sending') : t('cmp.send')}
        </button>
        <button type="button" className="btn ghost" onClick={() => setOpen(false)} aria-disabled={submit.busy}>
          {t('fin.back')}
        </button>
      </div>
    </form>
  )
}

export function Complaint() {
  const { id = '' } = useParams()
  const { t } = useLang()
  const { me, orgId } = useSession()
  const date = useDate()
  const location = useLocation()
  const c = useApi<CaseDetail>(`/orgs/${orgId}/cases/${id}`)
  const act = useSubmit()
  const [flash, setFlash] = useState<Key | null>((location.state as { flash?: Key } | null)?.flash ?? null)
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileKey, setFileKey] = useState(0) // a new key clears the file input after a save
  const [about, setAbout] = useState('')
  const [problem, setProblem] = useState<Key | null>(null)
  const [closing, setClosing] = useState(false)
  const back = <Link to="/complaints">← {t('nav.complaints')}</Link>

  if (c.error) return (<><PageHead title={t('nav.complaints')}>{back}</PageHead><ErrorState error={c.error} onRetry={c.retry} /></>)
  if (!c.data) return <Loading />
  const d = c.data
  const role = me!.memberships.find((m) => m.organization.id === orgId)?.role
  const contributor = role !== undefined && role !== 'viewer'
  const buyer = d.buyer_org_id === orgId && can(me!, orgId, 'buy')

  // `body` may be async: evidence details are hashed inside the same busy state as the send.
  const run = (path: string, body: () => object | Promise<object>, done: Key, after = () => {}) =>
    act.run(async () => {
      setFlash(null)
      try {
        await post(`/orgs/${orgId}/cases/${id}/${path}`, await body())
        after()
        setFlash(done)
      } catch (e) {
        // Support or the other party moved it on (for example it was resolved): show the current state.
        if (!(e instanceof ApiError && e.code === 'invalid_transition')) throw e
        setFlash('sup.case.changed')
      }
      c.retry()
    })
  const write = (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return setProblem('sup.case.needText')
    setProblem(null)
    void run('updates', () => ({ body: text.trim() }), 'cmp.sent', () => setText(''))
  }
  const attach = (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return setProblem('cmp.needFile')
    if (file.size === 0 || file.size > MAX_BYTES) return setProblem('cmp.fileSize')
    setProblem(null)
    void run('evidence', async () => ({ ...(await fileDetails(file)), description: about.trim() || null }), 'cmp.attached', () => (setFile(null), setAbout(''), setFileKey((k) => k + 1)))
  }

  return (
    <>
      <PageHead title={t('cmp.title', { ref: ref(d.id) })}>{back}</PageHead>
      {flash && (
        <p className="flash" role="status">
          {t(flash)}
        </p>
      )}
      <dl className="facts">
        <Fact label={t('sup.case.category')} value={t(`case.cat.${d.category}`)} />
        <Fact label={t('sup.urgency')} value={t(`urgency.${d.urgency}`)} />
        <Fact label={t('sup.case.status')} value={<Status kind="case" value={d.status} />} />
        <Fact label={t('sup.case.order')} value={<Link to={`/orders/${d.order_id}`}>{ref(d.order_id)}</Link>} />
        <Fact label={t('sup.case.opened')} value={date(d.created_at)} />
      </dl>
      <h2>{t('sup.case.description')}</h2>
      <p>{d.description}</p>
      {d.resolution && (
        <>
          <h2>{t('sup.case.resolution')}</h2>
          <p>{d.resolution}</p>
        </>
      )}
      {buyer && d.status === 'resolved' && (
        <section className="support-section" aria-labelledby="cmp-decide">
          <h2 id="cmp-decide">{t('cmp.decide')}</h2>
          <p className="note">{t('cmp.decideLead')}</p>
          {closing ? (
            <div className="confirm-box" role="group" aria-labelledby="cmp-close-ask">
              <p id="cmp-close-ask">{t('cmp.closeAsk')}</p>
              <div className="form-actions">
                <button type="button" className="btn primary" onClick={() => void run('close', () => ({}), 'cmp.closed', () => setClosing(false))} aria-disabled={act.busy}>
                  {t('cmp.closeYes')}
                </button>
                <button type="button" className="btn ghost" onClick={() => setClosing(false)} aria-disabled={act.busy}>
                  {t('fin.back')}
                </button>
              </div>
            </div>
          ) : (
            <div className="form-actions">
              <button type="button" className="btn primary" onClick={() => setClosing(true)}>
                {t('cmp.close')}
              </button>
              <button type="button" className="btn" onClick={() => void run('reopen', () => ({}), 'cmp.reopened')} aria-disabled={act.busy}>
                {t('cmp.reopen')}
              </button>
            </div>
          )}
        </section>
      )}

      {contributor && d.status !== 'closed' && <TalkToSupport caseId={d.id} urgency={d.urgency} />}

      <section className="support-section" aria-labelledby="cmp-messages">
        <h2 id="cmp-messages">{t('cmp.messages')}</h2>
        <p className="note">{t('cmp.messagesNote')}</p>
        {d.updates.length === 0 ? (
          <p className="note">{t('sup.case.none')}</p>
        ) : (
          <ol className="rows">
            {d.updates.map((u) => (
              <li key={u.id} className="msg">
                <span className="msg-who">
                  {t(u.author_id === me!.id ? 'sup.case.byYou' : 'cmp.byOther')} · <time dateTime={u.created_at}>{date(u.created_at)}</time>
                </span>
                <p>{u.body}</p>
              </li>
            ))}
          </ol>
        )}
        {contributor && d.status !== 'closed' && (
          <form onSubmit={write} noValidate>
            <label className="field">
              <span>{t('cmp.write')}</span>
              <textarea rows={3} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} aria-invalid={problem === 'sup.case.needText'} />
              {problem === 'sup.case.needText' && (
                <small className="field-error" role="alert">
                  {t(problem)}
                </small>
              )}
            </label>
            <div className="form-actions">
              <button type="submit" className="btn primary" aria-disabled={act.busy}>
                {act.busy ? t('state.sending') : t('cmp.sendMessage')}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="support-section" aria-labelledby="cmp-evidence">
        <h2 id="cmp-evidence">{t('sup.case.evidence')}</h2>
        <p className="note">{t('cmp.evidenceNote')}</p>
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
        {contributor && d.status !== 'closed' && (
          <form onSubmit={attach} noValidate>
            <label className="field">
              <span>{t('cmp.file')}</span>
              <input key={fileKey} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-invalid={problem === 'cmp.needFile' || problem === 'cmp.fileSize'} />
              {(problem === 'cmp.needFile' || problem === 'cmp.fileSize') && (
                <small className="field-error" role="alert">
                  {t(problem)}
                </small>
              )}
            </label>
            <label className="field">
              <span>{t('cmp.fileAbout')}</span>
              <input value={about} maxLength={500} onChange={(e) => setAbout(e.target.value)} />
            </label>
            <div className="form-actions">
              <button type="submit" className="btn" aria-disabled={act.busy}>
                {t('cmp.attach')}
              </button>
            </div>
          </form>
        )}
      </section>
      {act.error && <ErrorState error={act.error} />}
    </>
  )
}

/**
 * Hand a conversation to support with this complaint attached (SPEC.md 9.5 handoff case_id). The customer chooses:
 * a new, empty conversation (the default: nothing earlier is shared) or their latest conversation with the assistant,
 * whose last 10 messages the support person will then see. A conversation already with support is not offered.
 */
function TalkToSupport({ caseId, urgency }: { caseId: string; urgency: Case['urgency'] }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const navigate = useNavigate()
  const talk = useSubmit()
  const [share, setShare] = useState(false)
  const list = useApi<ConversationSummary[]>(`/orgs/${orgId}/conversations`).data
  const latest = list?.[0]
  const detail = useApi<ConversationDetail>(latest ? `/orgs/${orgId}/conversations/${latest.id}` : null).data
  const chat = list ? supportChatFor(list, caseId) : undefined
  const msgs = useApi<{ id: number; role: string; text: string; created_at: string }[]>(chat ? `/orgs/${orgId}/conversations/${chat.id}/messages?limit=20` : null).data
  const lastReply = msgs?.filter((m) => m.role === 'agent').at(-1)
  const busyWithSupport = !!detail?.handoff && detail.handoff.status !== 'released'
  const shareable = !!latest && !!detail && !busyWithSupport

  const go = () =>
    talk.run(async () => {
      const id = share && shareable ? latest.id : (await post<ConversationSummary>(`/orgs/${orgId}/conversations`)).id
      await post(`/orgs/${orgId}/conversations/${id}/handoff`, { case_id: caseId, urgency })
      navigate('/conversation', { state: { open: id } })
    })

  // One conversation per complaint: while support has one, open it instead of starting another.
  const openChat = chat && (
    <Link to="/conversation" state={{ open: chat.id }} className="btn primary">
      {t(chat.support_status === 'released' ? 'cmp.openLastChat' : 'cmp.openChat', { date: date(chat.created_at) })}
    </Link>
  )
  if (chat && chat.support_status !== 'released')
    return (
      <section className="support-section" aria-labelledby="cmp-talk">
        <h2 id="cmp-talk">{t('cmp.talkTitle')}</h2>
        <div className="callout" role="status">
          <p>{t('cmp.withSupport')}</p>
          {lastReply && (
            <blockquote className="last-reply">
              <strong>{t('cmp.lastReply')}</strong> {lastReply.text}
            </blockquote>
          )}
          <div className="form-actions">{openChat}</div>
        </div>
      </section>
    )

  return (
    <section className="support-section" aria-labelledby="cmp-talk">
      <h2 id="cmp-talk">{t('cmp.talkTitle')}</h2>
      {chat && (
        <div className="callout" role="status">
          <p>{t('cmp.supportDone')}</p>
          {lastReply && (
            <blockquote className="last-reply">
              <strong>{t('cmp.lastReply')}</strong> {lastReply.text}
            </blockquote>
          )}
          <div className="form-actions">{openChat}</div>
        </div>
      )}
      <p className="note">{t('cmp.talkLead')}</p>
      {shareable && (
        <fieldset className="choice">
          <legend>{t('cmp.shareLegend')}</legend>
          <label className="check">
            <input type="radio" name="share" checked={!share} onChange={() => setShare(false)} />
            {t('cmp.shareNew')}
          </label>
          <label className="check">
            <input type="radio" name="share" checked={share} onChange={() => setShare(true)} />
            {t('cmp.shareLatest', { date: date(latest.created_at) })}
          </label>
        </fieldset>
      )}
      {talk.error && <ErrorState error={talk.error} />}
      <div className="form-actions">
        <button type="button" className="btn" aria-disabled={talk.busy} onClick={go}>
          {talk.busy ? t('state.sending') : t('cmp.talk')}
        </button>
      </div>
    </section>
  )
}


import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError, post, useApi, type Order, type PaymentEvent, type PaymentRequest, type Payments, type Reversal } from '../api.ts'
import { useDate, useLang, type Key } from '../i18n.tsx'
import { can } from '../nav.ts'
import { toPaise } from '../rupees.ts'
import { useSession } from '../session.tsx'
import { ErrorState, Loading, Money, PageHead } from '../ui.tsx'
import { Fact, Status, useSubmit } from './Trade.tsx'

/** Simulated payments (SPEC.md 9.3). Nothing here moves real money; every figure is the API's. */
const ref = (id: string) => id.slice(0, 8)
const OPEN: PaymentRequest['status'][] = ['pending_approval', 'approved']
// Conflicts the API explains with a code: the page reloads and says what happened instead of failing.
const KNOWN = ['self_approval', 'terms_mismatch', 'invalid_transition', 'approval_expired', 'exceeds_outstanding', 'open_request_exists'] as const
const known = (e: unknown): e is ApiError => e instanceof ApiError && (KNOWN as readonly string[]).includes(e.code)

/** Balance, requests and saved events. `requestAction`/`eventAction` add finance controls beside a row. */
function Ledger({ p, requestAction, eventAction }: { p: Payments; requestAction?: (r: PaymentRequest) => ReactNode; eventAction?: (e: PaymentEvent) => ReactNode }) {
  const { t } = useLang()
  const date = useDate()
  return (
    <>
      <dl className="facts">
        <Fact label={t('pay.total')} value={<Money paise={p.total_paise} />} />
        <Fact label={t('pay.advance')} value={<Money paise={p.advance_paise} />} />
        <Fact label={t('pay.received')} value={<Money paise={p.received_paise} />} />
        <Fact label={t('pay.outstanding')} value={<Money paise={p.outstanding_paise} />} total />
        {p.refund_due_paise > 0 && <Fact label={t('pay.refundDue')} value={<Money paise={p.refund_due_paise} />} />}
      </dl>
      <h3>{t('pay.requests')}</h3>
      {p.requests.length === 0 ? (
        <p className="note">{t('pay.noRequests')}</p>
      ) : (
        <ul className="rows">
          {p.requests.map((r) => (
            <li key={r.id} className="row-card">
              <span className="row-main">
                <strong>
                  {t(`pay.purpose.${r.purpose}`)} · <Money paise={r.amount_paise} />
                </strong>
                <small>
                  {t('pay.asked', { when: date(r.created_at) })}
                  {r.status === 'approved' && r.approval_expires_at && ` · ${t('pay.recordBy', { when: date(r.approval_expires_at) })}`}
                </small>
                {r.decision_note && <span>{t('pay.note', { note: r.decision_note })}</span>}
              </span>
              <Status kind="payment" value={r.status} />
              {requestAction?.(r)}
            </li>
          ))}
        </ul>
      )}
      <h3>{t('pay.events')}</h3>
      {p.events.length === 0 ? (
        <p className="note">{t('pay.noEvents')}</p>
      ) : (
        <ul className="rows">
          {p.events.map((e) => (
            <li key={e.id} className="row-card">
              <span className="row-main">
                <strong>
                  {t(`pay.kind.${e.kind}`)} · <Money paise={e.amount_paise} />
                </strong>
                <small>{date(e.created_at)}</small>
                {e.reason && <span>{t('pay.reason', { reason: e.reason })}</span>}
              </span>
              {eventAction?.(e)}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** The payments block on an order, for both parties. Only a buyer admin/purchaser can report a payment. */
export function OrderPayments({ order }: { order: Order }) {
  const { t } = useLang()
  const { me, orgId } = useSession()
  const p = useApi<Payments>(`/orgs/${orgId}/orders/${order.id}/payments`)
  const [flash, setFlash] = useState<string | null>(null)
  const buyer = order.buyer_org_id === orgId && can(me!, orgId, 'buy')
  return (
    <section aria-labelledby="pay-title" className="quote-form">
      <h2 id="pay-title">{t('pay.title')}</h2>
      <p className="note">{t('pay.simulated')}</p>
      {flash && (
        <p className="flash" role="status">
          {flash}
        </p>
      )}
      {p.error ? (
        <ErrorState error={p.error} onRetry={p.retry} />
      ) : !p.data ? (
        <Loading />
      ) : (
        <>
          <Ledger p={p.data} />
          {buyer &&
            order.status === 'confirmed' &&
            p.data.outstanding_paise > 0 &&
            (p.data.requests.some((r) => OPEN.includes(r.status)) ? (
              <p className="note">{t('pay.openNote')}</p>
            ) : (
              <RequestForm order={order} p={p.data} onDone={(m) => (setFlash(m), p.retry())} />
            ))}
        </>
      )}
    </section>
  )
}

function RequestForm({ order, p, onDone }: { order: Order; p: Payments; onDone: (message: string) => void }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const submit = useSubmit()
  const [purpose, setPurpose] = useState<PaymentRequest['purpose']>(p.received_paise < p.advance_paise ? 'advance' : 'balance')
  const [amount, setAmount] = useState('')
  const [problem, setProblem] = useState<string | null>(null)

  const send = (e: React.FormEvent) => {
    e.preventDefault()
    const paise = toPaise(amount)
    if (!paise) return setProblem(t('pay.badAmount'))
    setProblem(null)
    void submit.run(async () => {
      try {
        // A retry after a lost response sends the same purpose and amount; the API returns the same open request.
        await post(`/orgs/${orgId}/orders/${order.id}/payment-requests`, { purpose, amount_paise: paise, quote_version: order.quote_version })
        setAmount('')
        onDone(t('pay.requested'))
      } catch (err) {
        if (err instanceof ApiError && err.code === 'exceeds_outstanding') {
          const left = Number(err.details?.advance_remaining_paise ?? err.details?.outstanding_paise ?? 0)
          return setProblem(t('pay.tooMuch', { amount: new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(left / 100) }))
        }
        if (known(err)) return onDone(t(`fin.err.${err.code}` as Key))
        throw err
      }
    })
  }

  return (
    <form onSubmit={send} noValidate>
      <h3>{t('pay.ask')}</h3>
      <p>{t('pay.askLead')}</p>
      <fieldset className="choice">
        <legend>{t('pay.purposeLabel')}</legend>
        {(['advance', 'balance'] as const).map((value) => (
          <label key={value} className="check">
            <input type="radio" name="purpose" value={value} checked={purpose === value} onChange={() => setPurpose(value)} />
            {t(`pay.purpose.${value}`)}
          </label>
        ))}
      </fieldset>
      <label className="field small">
        <span>{t('pay.amount')}</span>
        <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} aria-invalid={!!problem} aria-describedby={problem ? 'pay-err' : undefined} />
        {problem && (
          <small id="pay-err" className="field-error" role="alert">
            {problem}
          </small>
        )}
      </label>
      {submit.error && <ErrorState error={submit.error} />}
      <div className="form-actions">
        <button type="submit" className="btn primary" aria-disabled={submit.busy}>
          {submit.busy ? t('state.sending') : t('pay.send')}
        </button>
      </div>
    </form>
  )
}

/** A button that opens a confirmation showing the exact terms, with an optional or required text. */
function Act({ label, yes, ask, text, danger, confirm }: { label: Key; yes: Key; ask: ReactNode; text?: { label: Key; required: boolean }; danger?: boolean; confirm: (text: string) => Promise<void> }) {
  const { t } = useLang()
  const submit = useSubmit()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [missing, setMissing] = useState(false)
  if (!open)
    return (
      <button type="button" className={danger ? 'btn danger' : 'btn'} onClick={() => (submit.setError(null), setOpen(true))}>
        {t(label)}
      </button>
    )
  const go = () => {
    if (text?.required && !value.trim()) return setMissing(true)
    setMissing(false)
    void submit.run(async () => {
      await confirm(value.trim())
      setOpen(false)
    })
  }
  return (
    <div className="confirm-box" role="group" aria-label={t(label)}>
      {ask}
      {text && (
        <label className="field">
          <span>{t(text.label)}</span>
          <textarea rows={2} maxLength={500} value={value} onChange={(e) => setValue(e.target.value)} aria-invalid={missing} />
          {missing && (
            <small className="field-error" role="alert">
              {t('fin.needText')}
            </small>
          )}
        </label>
      )}
      {submit.error && <ErrorState error={submit.error} />}
      <div className="form-actions">
        <button type="button" className={danger ? 'btn danger' : 'btn primary'} onClick={go} aria-disabled={submit.busy}>
          {submit.busy ? t('state.sending') : t(yes)}
        </button>
        <button type="button" className="btn ghost" onClick={() => setOpen(false)} aria-disabled={submit.busy}>
          {t('fin.back')}
        </button>
      </div>
    </div>
  )
}

type List<T> = { data?: T[]; error?: ApiError; retry: () => void }

function QueueRows<T extends { id: string; order_id: string; amount_paise: number; created_at: string }>({ q, title, empty, label }: { q: List<T>; title: Key; empty: Key; label: (x: T) => string }) {
  const { t } = useLang()
  const date = useDate()
  return (
    <section className="support-section" aria-label={t(title)}>
      <h2>{t(title)}</h2>
      {q.error ? (
        <ErrorState error={q.error} onRetry={q.retry} />
      ) : !q.data ? (
        <Loading />
      ) : q.data.length === 0 ? (
        <p className="note">{t(empty)}</p>
      ) : (
        <ul className="rows">
          {q.data.map((x) => (
            <li key={x.id}>
              <Link to={`/finance/orders/${x.order_id}`} className="row-card">
                <span className="row-main">
                  <strong>
                    {label(x)} · <Money paise={x.amount_paise} />
                  </strong>
                  <small>
                    {t('fin.order', { ref: ref(x.order_id) })} · {date(x.created_at)}
                  </small>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function FinanceQueue() {
  const { t } = useLang()
  const pending = useApi<PaymentRequest[]>('/staff/payment-requests?status=pending_approval')
  const approved = useApi<PaymentRequest[]>('/staff/payment-requests?status=approved')
  const reversals = useApi<Reversal[]>('/staff/payment-reversals?status=pending_approval')
  const purpose = (r: PaymentRequest) => t(`pay.purpose.${r.purpose}`)
  return (
    <>
      <PageHead title={t('nav.finance')} lead={t('fin.lead')} />
      <p className="note">{t('pay.simulated')}</p>
      <QueueRows q={pending} title="fin.pending" empty="fin.none" label={purpose} />
      <QueueRows q={approved} title="fin.approved" empty="fin.none" label={purpose} />
      <QueueRows q={reversals} title="fin.reversals" empty="fin.none" label={() => t('pay.kind.reversal')} />
    </>
  )
}

export function FinanceOrder() {
  const { id = '' } = useParams()
  const { t } = useLang()
  const { me } = useSession()
  const date = useDate()
  const p = useApi<Payments>(`/staff/orders/${id}/payments`)
  const revs = useApi<Reversal[]>('/staff/payment-reversals?status=pending_approval&limit=100')
  const [flash, setFlash] = useState<Key | null>(null)
  const back = <Link to="/finance">← {t('fin.back.queue')}</Link>

  if (p.error) return (<><PageHead title={t('fin.orderTitle', { ref: ref(id) })}>{back}</PageHead><ErrorState error={p.error} onRetry={p.retry} /></>)
  if (!p.data) return <Loading />
  const d = p.data
  const pendingFor = (e: PaymentEvent) => revs.data?.find((r) => r.order_id === id && r.receipt_event_id === e.id)
  const reversed = (e: PaymentEvent) => d.events.some((x) => x.reverses_event_id === e.id)

  const act = (path: string, body: object, done: Key) => async () => {
    setFlash(null)
    try {
      await post(path, body)
      setFlash(done)
    } catch (e) {
      if (!known(e)) throw e
      setFlash(`fin.err.${e.code}` as Key)
    }
    p.retry()
    revs.retry()
  }
  const terms = (rows: [Key, ReactNode][]) => (
    <dl className="facts">
      {rows.map(([label, value]) => (
        <Fact key={label} label={t(label)} value={value} />
      ))}
    </dl>
  )

  const requestAction = (r: PaymentRequest) => {
    const exact = terms([
      ['fin.orderRef', ref(r.order_id)],
      ['pay.purposeLabel', t(`pay.purpose.${r.purpose}`)],
      ['pay.amount', <Money key="amount" paise={r.amount_paise} />],
      ['confirm.version', String(r.quote_version)],
    ])
    if (r.status === 'pending_approval')
      return (
        <div className="form-actions">
          <Act
            label="fin.approve"
            yes="fin.approveYes"
            ask={<><p>{t('fin.approveAsk')}</p>{exact}</>}
            text={{ label: 'fin.noteOptional', required: false }}
            confirm={(note) => act(`/staff/payment-requests/${r.id}/approve`, { order_id: r.order_id, purpose: r.purpose, amount_paise: r.amount_paise, quote_version: r.quote_version, note: note || null }, 'fin.approved.done')()}
          />
          <Act
            label="fin.reject"
            yes="fin.rejectYes"
            danger
            ask={<p>{t('fin.rejectAsk')}</p>}
            text={{ label: 'fin.noteRequired', required: true }}
            confirm={(note) => act(`/staff/payment-requests/${r.id}/reject`, { note }, 'fin.rejected.done')()}
          />
        </div>
      )
    if (r.status === 'approved')
      return (
        <Act
          label="fin.record"
          yes="fin.recordYes"
          ask={<><p>{t('fin.recordAsk')}</p>{exact}</>}
          confirm={() => act(`/staff/payment-requests/${r.id}/record`, {}, 'fin.recorded.done')()}
        />
      )
    return null
  }

  const eventAction = (e: PaymentEvent) => {
    if (e.kind !== 'receipt' || reversed(e)) return null
    const rev = pendingFor(e)
    if (!rev)
      return (
        <Act
          label="fin.reverse"
          yes="fin.reverseYes"
          danger
          ask={<p>{t('fin.reverseAsk')}</p>}
          text={{ label: 'fin.reasonRequired', required: true }}
          confirm={(reason) => act(`/staff/payment-events/${e.id}/reverse`, { reason }, 'fin.reverse.done')()}
        />
      )
    return (
      <div className="confirm-box">
        <p>
          <strong>{t('fin.reversalWaiting')}</strong> {t('pay.reason', { reason: rev.reason })} · {t('pay.recordBy', { when: date(rev.expires_at) })}
        </p>
        {/* Maker-checker: the person who asked cannot decide (the API refuses with 403 self_approval). */}
        {rev.requested_by === me!.id ? (
          <p className="note">{t('fin.otherPerson')}</p>
        ) : (
          <div className="form-actions">
            <Act
              label="fin.approveReversal"
              yes="fin.approveReversalYes"
              danger
              ask={<><p>{t('fin.approveReversalAsk')}</p>{terms([['fin.orderRef', ref(rev.order_id)], ['pay.amount', <Money key="amount" paise={rev.amount_paise} />], ['fin.reasonLabel', rev.reason]])}</>}
              text={{ label: 'fin.noteOptional', required: false }}
              confirm={(note) => act(`/staff/payment-reversals/${rev.id}/approve`, { order_id: rev.order_id, receipt_event_id: rev.receipt_event_id, amount_paise: rev.amount_paise, reason: rev.reason, note: note || null }, 'fin.reversed.done')()}
            />
            <Act
              label="fin.reject"
              yes="fin.rejectYes"
              ask={<p>{t('fin.rejectReversalAsk')}</p>}
              text={{ label: 'fin.noteRequired', required: true }}
              confirm={(note) => act(`/staff/payment-reversals/${rev.id}/reject`, { note }, 'fin.rejected.done')()}
            />
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      <PageHead title={t('fin.orderTitle', { ref: ref(id) })}>{back}</PageHead>
      <p className="note">{t('pay.simulated')}</p>
      {flash && (
        <p className="flash" role="status">
          {t(flash)}
        </p>
      )}
      <dl className="facts">
        <Fact label={t('order.status')} value={<Status kind="order" value={d.order_status} />} />
      </dl>
      <Ledger p={d} requestAction={requestAction} eventAction={eventAction} />
    </>
  )
}

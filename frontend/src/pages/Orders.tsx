import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { ApiError, post, useApi, type Order } from '../api.ts'
import { actionsFor, type FulfilmentAction } from '../fulfilment.ts'
import { useDate, useLang, type Key } from '../i18n.tsx'
import { useSession } from '../session.tsx'
import { Empty, ErrorState, Loading, Money, PageHead } from '../ui.tsx'
import { OpenComplaint } from './Complaints.tsx'
import { OrderPayments } from './Finance.tsx'
import { Fact, Spec, Status, Terms, useSubmit } from './Trade.tsx'

export function Orders() {
  const { t, lang } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const { data, error, loading, retry } = useApi<Order[]>(`/orgs/${orgId}/orders`)
  return (
    <>
      <PageHead title={t('nav.orders')} lead={t('order.listLead')} />
      {error && <ErrorState error={error} onRetry={retry} />}
      {loading && <Loading />}
      {data && !loading && !error &&
        (data.length === 0 ? (
          <Empty title={t('order.emptyTitle')} text={t('order.empty')} />
        ) : (
          <ul className="rows">
            {data.map((o) => {
              const bought = o.buyer_org_id === orgId
              const s = o.product_snapshot
              return (
                <li key={o.id}>
                  <Link to={`/orders/${o.id}`} className="row-card">
                    <span className="row-main">
                      <strong>{lang === 'te' && s.name_te ? s.name_te : s.name}</strong>
                      <span>
                        {t(bought ? 'order.boughtFrom' : 'order.soldTo', { org: bought ? o.seller_org_name : o.buyer_org_name })} · {o.quantity} × {t(`unit.${s.unit}`)} · <Money paise={o.total_paise} />
                      </span>
                      <small>{date(o.created_at)}</small>
                    </span>
                    <Status kind="order" value={o.status} />
                  </Link>
                </li>
              )
            })}
          </ul>
        ))}
    </>
  )
}

export function OrderView() {
  const { id } = useParams()
  const { t, lang } = useLang()
  const { me, orgId } = useSession()
  const date = useDate()
  const [flash, setFlash] = useState<string | null>(((k) => (k ? t(k) : null))((useLocation().state as { flash?: Key } | null)?.flash))
  const { data: o, error, loading, retry } = useApi<Order>(`/orgs/${orgId}/orders/${encodeURIComponent(id!)}`)
  const back = (
    <Link to="/orders" className="back">
      ← {t('nav.orders')}
    </Link>
  )
  if (error) return (<><PageHead title={t('order.title')}>{back}</PageHead><ErrorState error={error} onRetry={retry} /></>)
  if (loading || !o || o.id !== id) return (<><PageHead title={t('order.title')}>{back}</PageHead><Loading /></>)
  const s = o.product_snapshot
  return (
    <>
      <PageHead title={lang === 'te' && s.name_te ? s.name_te : s.name} lead={t('order.lead')}>
        {back}
      </PageHead>
      {flash && (
        <p className="flash" role="status">
          {flash}
        </p>
      )}
      <dl className="facts">
        <Fact label={t('order.status')} value={<Status kind="order" value={o.status} />} />
        <Fact label={t('order.delivery')} value={<Status kind="fulfil" value={o.fulfillment_status} />} />
        <Fact label={t('rfq.buyer')} value={o.buyer_org_name} />
        <Fact label={t('rfq.seller')} value={o.seller_org_name} />
        <Fact label={t('confirm.version')} value={String(o.quote_version)} />
        <Fact label={t('order.confirmedAt')} value={date(o.created_at)} />
      </dl>
      <h2>{t('order.terms')}</h2>
      <Spec s={s} />
      <Terms money={o} unit={t(`unit.${s.unit}`)} />
      <p className="note">{t('order.simulated')}</p>
      {/* key: a changed order state reloads the timeline from the server */}
      <Fulfilment
        key={`${orgId}:${o.id}:${o.status}:${o.fulfillment_status}`}
        order={o}
        role={me!.memberships.find((m) => m.organization.id === orgId)?.role}
        onChange={(message) => (setFlash(message), retry())}
      />
      <OrderPayments key={`${orgId}:${o.id}:${o.status}`} order={o} />
      <OpenComplaint key={`${orgId}:${o.id}`} order={o} />
    </>
  )
}

type FulfilmentEvent = { id: string; status: string; note: string | null; created_at: string }
const STEPS = ['pending', 'dispatched', 'delivered', 'accepted'] as const

function Fulfilment({ order: o, role, onChange }: { order: Order; role: Parameters<typeof actionsFor>[2]; onChange: (message: string) => void }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const events = useApi<FulfilmentEvent[]>(`/orgs/${orgId}/orders/${o.id}/fulfillment-events`)
  const side = o.seller_org_id === orgId ? 'seller' : 'buyer'
  const actions = actionsFor(o, side, role)
  const submit = useSubmit()
  const [open, setOpen] = useState<FulfilmentAction | null>(null)
  const [text, setText] = useState('')
  const [textError, setTextError] = useState('')
  const opener = useRef<Record<string, HTMLButtonElement | null>>({})
  const ask = useRef<HTMLParagraphElement>(null)
  const last = useRef<FulfilmentAction | null>(null)
  useEffect(() => {
    // Focus moves only when a confirmation opens or closes, never on busy/error re-renders.
    if (open) ask.current?.focus()
    else if (last.current) opener.current[last.current]?.focus()
    last.current = open
  }, [open])

  const reached = STEPS.indexOf(o.fulfillment_status)
  const confirm = () => {
    if (!open) return
    if (open === 'cancel' && !text.trim()) return setTextError(t('ful.reasonRequired'))
    submit.run(async () => {
      try {
        const path = open === 'cancel' ? 'cancel' : 'fulfillment'
        const body = open === 'cancel' ? { reason: text.trim() } : { action: open, note: text.trim() || null }
        await post(`/orgs/${orgId}/orders/${o.id}/${path}`, body)
        onChange(t(`ful.done.${open}`))
      } catch (e) {
        // Someone else moved the order on first: show the latest state instead of an error.
        if (e instanceof ApiError && e.code === 'invalid_transition') return onChange(t('ful.changed'))
        throw e
      }
    })
  }
  return (
    <section aria-labelledby="ful-title" className="quote-form">
      <h2 id="ful-title">{t('ful.title')}</h2>
      {o.status === 'cancelled' ? (
        <p className="flash">{t('ful.cancelled')}</p>
      ) : (
        <ol className="steps-line">
          {STEPS.map((step, i) => (
            <li key={step} className={i <= reached ? 'done' : ''} aria-current={i === reached ? 'step' : undefined}>
              {t(`status.fulfil.${step}`)}
            </li>
          ))}
        </ol>
      )}
      {events.error && <ErrorState error={events.error} onRetry={events.retry} />}
      {events.data && events.data.length > 0 && (
        <ul className="rows history">
          {events.data.map((e) => (
            <li key={e.id} className="row-card">
              <span className="row-main">
                <strong>{t(`ful.event.${e.status}` as Key)}</strong>
                <small>
                  {date(e.created_at)}
                  {e.note && ` · ${e.note}`}
                </small>
              </span>
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <div className="review" role="group" aria-labelledby="ful-ask">
          <p id="ful-ask" tabIndex={-1} ref={ask}>
            {t(`ful.ask.${open}`)}
          </p>
          <label className="field">
            <span>{t(open === 'cancel' ? 'ful.reason' : 'ful.note')}</span>
            <textarea
              rows={2}
              maxLength={500}
              value={text}
              aria-invalid={!!textError}
              aria-describedby={textError ? 'ful-text-err' : undefined}
              onChange={(e) => setText(e.target.value)}
            />
            {textError && (
              <small id="ful-text-err" className="field-error">
                {textError}
              </small>
            )}
          </label>
          {submit.error && <ErrorState error={submit.error} />}
          <div className="form-actions">
            <button type="button" className={open === 'cancel' ? 'btn danger' : 'btn primary'} onClick={confirm} aria-disabled={submit.busy}>
              {submit.busy ? t('state.sending') : t(`ful.confirm.${open}`)}
            </button>
            <button type="button" className="btn ghost" onClick={() => !submit.busy && setOpen(null)} aria-disabled={submit.busy}>
              {t('confirm.back')}
            </button>
          </div>
        </div>
      ) : actions.length > 0 ? (
        <div className="form-actions">
          {actions.map((a) => (
            <button
              key={a}
              type="button"
              className={a === 'cancel' ? 'btn danger' : 'btn primary'}
              ref={(el) => void (opener.current[a] = el)}
              onClick={() => (setText(''), setTextError(''), submit.setError(null), setOpen(a))}
            >
              {t(`ful.action.${a}`)}
            </button>
          ))}
        </div>
      ) : (
        o.status === 'confirmed' && <p className="note">{t(side === 'buyer' ? 'ful.waitSeller' : 'ful.waitBuyer')}</p>
      )}
      <p className="note">{t('ful.paymentSeparate')}</p>
    </section>
  )
}

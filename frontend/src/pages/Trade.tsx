import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError, post, useApi, type Order, type Product, type Quote, type Rfq, type RfqDetail, type Snapshot } from '../api.ts'
import { productName, useDate, useLang, type Key } from '../i18n.tsx'
import { can } from '../nav.ts'
import { toPaise } from '../rupees.ts'
import { useSession } from '../session.tsx'
import { Empty, ErrorState, Loading, Money, PageHead } from '../ui.tsx'

const VALID_DAYS = [1, 3, 7, 14]

/** Runs one write at a time and keeps its error, so typed input stays on screen after a recoverable failure. */
export function useSubmit() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const run = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, 'network', ''))
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, setError, run }
}


/* ---------- Buyer: request a quote from a product ---------- */

export function RequestQuote() {
  const { id } = useParams()
  const { t, lang } = useLang()
  const { me, orgId } = useSession()
  const navigate = useNavigate()
  const { data: p, error, loading, retry } = useApi<Product>(`/catalog/products/${encodeURIComponent(id!)}`)
  const submit = useSubmit()
  const [qtyError, setQtyError] = useState('')
  // One key per request intent, reused for retries so a lost response cannot create a second enquiry.
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [alreadySent, setAlreadySent] = useState(false)

  const back = (
    <Link to={`/products/${id}`} className="back">
      ← {t('rfq.backToProduct')}
    </Link>
  )
  if (error) return (<><PageHead title={t('rfq.new')}>{back}</PageHead><ErrorState error={error} onRetry={retry} /></>)
  if (loading || !p) return (<><PageHead title={t('rfq.new')}>{back}</PageHead><Loading /></>)
  if (!can(me!, orgId, 'buy') || p.seller.id === orgId)
    return (<><PageHead title={t('rfq.new')}>{back}</PageHead><Empty title={t('perm.title')} text={t('perm.buy')} /></>)

  const unit = t(`unit.${p.unit}`)
  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const quantity = Number(f.get('quantity'))
    if (!Number.isInteger(quantity) || quantity < p.moq) return setQtyError(t('rfq.qtyMin', { n: p.moq, unit }))
    setQtyError('')
    const note = String(f.get('note')).trim()
    setAlreadySent(false)
    submit.run(async () => {
      try {
        const body = { product_id: p.id, quantity, delivery_city: String(f.get('delivery_city')).trim(), needed_by: f.get('needed_by') || null, note: note || null }
        const rfq = await post<Rfq>(`/orgs/${orgId}/rfqs`, body, { 'Idempotency-Key': key })
        navigate(`/requests/${rfq.id}`, { state: { flash: 'rfq.sent' } })
      } catch (e) {
        // An earlier attempt with this key reached the seller with different details; a further press is a new request.
        if (!(e instanceof ApiError && e.code === 'idempotency_key_reused')) throw e
        setKey(crypto.randomUUID())
        setAlreadySent(true)
      }
    })
  }
  return (
    <>
      <PageHead title={t('rfq.new')} lead={t('rfq.newLead')}>
        {back}
      </PageHead>
      <p className="summary-line">
        <strong>{productName(lang, p)}</strong> · {p.seller.name} · <Money paise={p.price_paise} /> {t('product.per', { unit })}
      </p>
      <form className="stack-form" onSubmit={onSubmit} noValidate>
        <label className="field">
          <span>{t('rfq.quantity', { unit })}</span>
          <input
            name="quantity"
            type="number"
            inputMode="numeric"
            min={p.moq}
            defaultValue={p.moq}
            required
            aria-invalid={!!qtyError}
            aria-describedby="qty-help"
          />
          <small id="qty-help" className={qtyError ? 'field-error' : 'hint'}>
            {qtyError || t('rfq.qtyHint', { n: p.moq, unit, stock: p.available_qty })}
          </small>
        </label>
        <label className="field">
          <span>{t('rfq.city')}</span>
          <input name="delivery_city" list="cities" maxLength={80} required defaultValue={p.delivery_cities[0] ?? ''} />
          <datalist id="cities">
            {p.delivery_cities.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label className="field">
          <span>{t('rfq.neededBy')}</span>
          <input name="needed_by" type="date" />
        </label>
        <label className="field">
          <span>{t('rfq.note')}</span>
          <textarea name="note" maxLength={500} rows={3} />
        </label>
        {submit.error && <ErrorState error={submit.error} />}
        {alreadySent && (
          <p className="flash" role="status">
            {t('rfq.alreadySent')} <Link to="/requests">{t('nav.requests')}</Link>
          </p>
        )}
        <div className="form-actions">
          <button type="submit" className="btn primary" aria-disabled={submit.busy}>
            {submit.busy ? t('state.sending') : t('rfq.submit')}
          </button>
        </div>
        <p className="note">{t('rfq.nothingBought')}</p>
      </form>
    </>
  )
}

/* ---------- Lists: buyer requests and seller enquiries ---------- */

export function RfqList({ side }: { side: 'buyer' | 'seller' }) {
  const { t, lang } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const { data, error, loading, retry } = useApi<Rfq[]>(`/orgs/${orgId}/rfqs`)
  const mine = data?.filter((r) => (side === 'buyer' ? r.buyer_org_id : r.seller_org_id) === orgId) ?? []
  const base = side === 'buyer' ? '/requests' : '/enquiries'
  return (
    <>
      <PageHead title={t(side === 'buyer' ? 'nav.requests' : 'nav.enquiries')} lead={t(side === 'buyer' ? 'rfq.listLeadBuyer' : 'rfq.listLeadSeller')} />
      {error && <ErrorState error={error} onRetry={retry} />}
      {loading && <Loading />}
      {data && !loading && !error &&
        (mine.length === 0 ? (
          <Empty title={t('rfq.emptyTitle')} text={t(side === 'buyer' ? 'rfq.emptyBuyer' : 'rfq.emptySeller')} />
        ) : (
          <ul className="rows">
            {mine.map((r) => (
              <li key={r.id}>
                <Link to={`${base}/${r.id}`} className="row-card">
                  <span className="row-main">
                    <strong>{productName(lang, { name: r.product_name, name_te: r.product_name_te })}</strong>
                    <span>
                      {side === 'buyer' ? r.seller_org_name : r.buyer_org_name} · {r.quantity} × {t(`unit.${r.product_unit}`)} · {r.delivery_city}
                    </span>
                    <small>{date(r.created_at)}</small>
                  </span>
                  <Status kind="rfq" value={r.status} />
                </Link>
              </li>
            ))}
          </ul>
        ))}
      {side === 'buyer' && (
        <Link to="/products" className="btn more">
          {t('rfq.findMore')}
        </Link>
      )}
    </>
  )
}

export function Status({ kind, value }: { kind: 'rfq' | 'quote' | 'order' | 'fulfil' | 'case' | 'handoff' | 'payment'; value: string }) {
  const { t } = useLang()
  return <span className={`status status-${value}`}>{t(`status.${kind}.${value}` as Key)}</span>
}

/* ---------- RFQ detail with quotes: both sides ---------- */

export function RfqView() {
  const { id } = useParams()
  const { t, lang } = useLang()
  const { me, orgId } = useSession()
  const date = useDate()
  const location = useLocation()
  const [flash, setFlash] = useState<Key | null>((location.state as { flash?: Key } | null)?.flash ?? null)
  const { data: rfq, error, loading, retry } = useApi<RfqDetail>(`/orgs/${orgId}/rfqs/${encodeURIComponent(id!)}`)
  const isBuyer = rfq?.buyer_org_id === orgId
  const base = location.pathname.startsWith('/enquiries') ? '/enquiries' : '/requests'
  const back = (
    <Link to={base} className="back">
      ← {t(base === '/enquiries' ? 'nav.enquiries' : 'nav.requests')}
    </Link>
  )
  if (error) return (<><PageHead title={t('rfq.title')}>{back}</PageHead><ErrorState error={error} onRetry={retry} /></>)
  if (loading || !rfq || rfq.id !== id) return (<><PageHead title={t('rfq.title')}>{back}</PageHead><Loading /></>)

  const unit = t(`unit.${rfq.product_unit}`)
  const reload = (k: Key | null) => {
    setFlash(k)
    retry()
  }
  const newest = rfq.quotes.at(-1)
  const open = rfq.status === 'open' || rfq.status === 'quoted'
  return (
    <>
      <PageHead title={productName(lang, { name: rfq.product_name, name_te: rfq.product_name_te })} lead={t(isBuyer ? 'rfq.leadBuyer' : 'rfq.leadSeller', { org: isBuyer ? rfq.seller_org_name : rfq.buyer_org_name })}>
        {back}
      </PageHead>
      {flash && (
        <p className="flash" role="status">
          {t(flash)}
        </p>
      )}
      <dl className="facts">
        <Fact label={t('rfq.status')} value={<Status kind="rfq" value={rfq.status} />} />
        <Fact label={t('rfq.quantityLabel')} value={`${rfq.quantity} × ${unit}`} />
        <Fact label={t('rfq.city')} value={rfq.delivery_city} />
        <Fact label={t('rfq.neededByShort')} value={rfq.needed_by ?? '—'} />
        <Fact label={t('rfq.buyer')} value={rfq.buyer_org_name} />
        <Fact label={t('rfq.seller')} value={rfq.seller_org_name} />
        <Fact label={t('rfq.created')} value={date(rfq.created_at)} />
        {rfq.note && <Fact label={t('rfq.noteShort')} value={rfq.note} />}
      </dl>

      <section aria-labelledby="quotes-title" className="quotes">
        <h2 id="quotes-title">{t('quote.heading')}</h2>
        {rfq.quotes.length === 0 && <p className="note">{t(isBuyer ? 'quote.noneBuyer' : 'quote.noneSeller')}</p>}
        {[...rfq.quotes].reverse().map((q) => (
          <article key={q.id} className={`quote-card ${q.status === 'sent' ? 'current' : ''}`} aria-labelledby={`q-${q.id}`}>
            <header>
              <h3 id={`q-${q.id}`}>{t('quote.version', { n: q.version })}</h3>
              <Status kind="quote" value={q.status} />
            </header>
            <Terms money={q} unit={unit} />
            <p className="hint">
              {t('quote.validUntil', { when: date(q.valid_until) })}
              {q.sent_at && ` · ${t('quote.sentAt', { when: date(q.sent_at) })}`}
            </p>
            {isBuyer && q.status === 'sent' &&
              (can(me!, orgId, 'buy') ? <BuyerActions quote={q} rfq={rfq} onChange={reload} /> : <p className="note">{t('perm.viewOnly')}</p>)}
            {!isBuyer && q.status === 'draft' && q === newest && open &&
              (can(me!, orgId, 'sell') ? <SendDraft quote={q} onChange={reload} /> : <p className="note">{t('perm.viewOnly')}</p>)}
          </article>
        ))}
      </section>

      {!isBuyer && open && (can(me!, orgId, 'sell') ? <QuoteForm rfq={rfq} onDone={reload} /> : <p className="note">{t('perm.viewOnly')}</p>)}
      {rfq.status === 'closed' && <ClosedNote rfq={rfq} />}
    </>
  )
}

function ClosedNote({ rfq }: { rfq: RfqDetail }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const accepted = rfq.quotes.find((q) => q.status === 'accepted')
  const orders = useApi<Order[]>(accepted ? `/orgs/${orgId}/orders` : null)
  const order = orders.data?.find((o) => o.quote_id === accepted?.id)
  return (
    <p className="flash">
      {t('rfq.closed')} {order && <Link to={`/orders/${order.id}`}>{t('rfq.openOrder')}</Link>}
    </p>
  )
}

export function Terms({ money: m, unit }: { money: Quote | Order; unit: string }) {
  const { t } = useLang()
  return (
    <dl className="terms">
      <Fact label={t('terms.unitPrice')} value={<><Money paise={m.unit_price_paise} /> × {m.quantity} {unit}</>} />
      {m.discount_paise > 0 && <Fact label={t('terms.discount')} value={<>− <Money paise={m.discount_paise} /></>} />}
      <Fact label={t('terms.subtotal')} value={<Money paise={m.subtotal_paise} />} />
      <Fact label={t('terms.freight')} value={<Money paise={m.freight_paise} />} />
      <Fact label={t('terms.tax', { pct: m.tax_bp / 100 })} value={<Money paise={m.tax_paise} />} />
      <Fact label={t('terms.total')} value={<strong><Money paise={m.total_paise} /></strong>} total />
      <Fact label={t('terms.advance')} value={<Money paise={m.advance_paise} />} />
    </dl>
  )
}

export function Spec({ s }: { s: Snapshot }) {
  const { t, lang } = useLang()
  const unit = t(`unit.${s.unit}`)
  return (
    <dl className="facts">
      <Fact label={t('terms.product')} value={productName(lang, s)} />
      <Fact label="SKU" value={`${s.sku} · ${s.brand} ${s.model}`} />
      <Fact label={t('product.rating')} value={`${s.rating_amps} A · ${s.voltage_v} V · ${s.ways === 1 ? t('products.oneWay') : t('products.twoWay')}`} />
      <Fact label={t('product.pack')} value={s.unit === 'box' ? `${s.pack_size} / ${unit}` : `1 ${unit}`} />
    </dl>
  )
}

export const Fact = ({ label, value, total }: { label: string; value: React.ReactNode; total?: boolean }) => (
  <div className={total ? 'fact total' : 'fact'}>
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
)

/* ---------- Buyer: reject, or review and explicitly confirm ---------- */

const REASONS = ['already_accepted', 'superseded', 'not_sent', 'expired', 'total_mismatch', 'product_changed'] as const

export function BuyerActions({ quote: q, rfq, onChange }: { quote: Quote; rfq: RfqDetail; onChange: (k: Key | null) => void }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const navigate = useNavigate()
  const submit = useSubmit()
  const [step, setStep] = useState<'idle' | 'review' | 'reject'>('idle')
  // One key per confirm intent (this quote version). A retry after a lost response reuses it, so the API replays instead of ordering twice.
  const [key, setKey] = useState('')
  const unit = t(`unit.${q.product_snapshot.unit}`)
  // Move focus only when the step changes; busy and error re-renders leave it on the control the person is using.
  const heading = useRef<HTMLHeadingElement>(null)
  const ask = useRef<HTMLParagraphElement>(null)
  const reviewButton = useRef<HTMLButtonElement>(null)
  const rejectButton = useRef<HTMLButtonElement>(null)
  const previous = useRef(step)
  useEffect(() => {
    const was = previous.current
    previous.current = step
    if (was === step) return
    if (step === 'review') heading.current?.focus()
    else if (step === 'reject') ask.current?.focus()
    else (was === 'review' ? reviewButton : rejectButton).current?.focus()
  }, [step])
  const leave = () => !submit.busy && setStep('idle')

  const conflict = (e: unknown) => {
    if (e instanceof ApiError && e.code === 'quote_not_confirmable') {
      const r = String(e.details?.reason ?? '')
      onChange(REASONS.includes(r as (typeof REASONS)[number]) ? (`confirm.${r}` as Key) : 'confirm.changed')
      return true
    }
    return false
  }
  const confirm = () =>
    submit.run(async () => {
      try {
        const order = await post<Order>(`/orgs/${orgId}/orders`, { quote_id: q.id, quote_version: q.version, total_paise: q.total_paise }, { 'Idempotency-Key': key })
        navigate(`/orders/${order.id}`, { state: { flash: 'order.confirmed' } })
      } catch (e) {
        if (!conflict(e)) throw e
      }
    })
  const reject = () =>
    submit.run(async () => {
      try {
        await post(`/orgs/${orgId}/quotes/${q.id}/reject`)
        onChange('quote.rejectedFlash')
      } catch (e) {
        // Any conflict means the quote moved on (accepted, superseded or expired): reload current terms.
        if (e instanceof ApiError && e.status === 409) return onChange('confirm.changed')
        throw e
      }
    })

  if (step === 'reject')
    return (
      <div className="confirm-box" role="group" aria-labelledby={`rj-${q.id}`}>
        <p id={`rj-${q.id}`} tabIndex={-1} ref={ask}>
          {t('quote.rejectAsk', { n: q.version })}
        </p>
        {submit.error && <ErrorState error={submit.error} />}
        <div className="form-actions">
          <button type="button" className="btn danger" onClick={reject} aria-disabled={submit.busy}>
            {t('quote.rejectYes')}
          </button>
          <button type="button" className="btn ghost" onClick={leave} aria-disabled={submit.busy}>
            {t('quote.keep')}
          </button>
        </div>
      </div>
    )
  if (step === 'review')
    return (
      <section className="review" aria-labelledby={`rv-${q.id}`}>
        <h3 id={`rv-${q.id}`} tabIndex={-1} ref={heading}>
          {t('confirm.title')}
        </h3>
        <p>{t('confirm.lead', { org: rfq.seller_org_name })}</p>
        <Spec s={q.product_snapshot} />
        <dl className="facts">
          <Fact label={t('rfq.quantityLabel')} value={`${q.quantity} × ${unit}`} />
          <Fact label={t('rfq.city')} value={rfq.delivery_city} />
          <Fact label={t('confirm.version')} value={String(q.version)} />
        </dl>
        <Terms money={q} unit={unit} />
        <p className="note">{t('confirm.simulated')}</p>
        {submit.error && <ErrorState error={submit.error} />}
        <div className="form-actions">
          {/* aria-disabled, not disabled: a disabled button drops keyboard focus to the page while the request runs. */}
          <button type="button" className="btn primary" onClick={confirm} aria-disabled={submit.busy}>
            {submit.busy ? t('state.sending') : t('confirm.button')}
          </button>
          <button type="button" className="btn ghost" onClick={leave} aria-disabled={submit.busy}>
            {t('confirm.back')}
          </button>
        </div>
      </section>
    )
  return (
    <div className="form-actions">
      <button
        type="button"
        className="btn primary"
        ref={reviewButton}
        onClick={() => {
          setKey(crypto.randomUUID())
          submit.setError(null)
          setStep('review')
        }}
      >
        {t('quote.review')}
      </button>
      <button type="button" className="btn ghost" ref={rejectButton} onClick={() => (submit.setError(null), setStep('reject'))}>
        {t('quote.reject')}
      </button>
    </div>
  )
}

/* ---------- Seller: draft a quote, check backend totals, then send ---------- */

function QuoteForm({ rfq, onDone }: { rfq: RfqDetail; onDone: (k: Key | null) => void }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const submit = useSubmit()
  const [errors, setErrors] = useState<Record<string, string>>({})
  const list = useApi<Product>(`/catalog/products/${rfq.product_id}`)
  // The list price only suggests a value; once the seller types, their text wins and nothing remounts the form.
  const [price, setPrice] = useState<string | null>(null)
  const listPrice = list.data ? (list.data.price_paise / 100).toFixed(2) : ''
  const unit = t(`unit.${rfq.product_unit}`)

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const f = new FormData(form)
    const amounts: Record<string, number | null> = {}
    const errs: Record<string, string> = {}
    for (const k of ['unit_price', 'discount', 'freight', 'advance']) {
      const raw = String(f.get(k) ?? '').trim()
      amounts[k] = raw === '' && k !== 'unit_price' ? 0 : toPaise(raw)
      if (amounts[k] === null || (k === 'unit_price' && amounts[k] === 0)) errs[k] = t('quote.amountError')
    }
    setErrors(errs)
    if (Object.keys(errs).length) return
    const days = Number(f.get('valid_days'))
    submit.run(async () => {
      await post<Quote>(`/orgs/${orgId}/rfqs/${rfq.id}/quotes`, {
        unit_price_paise: amounts.unit_price,
        discount_paise: amounts.discount,
        freight_paise: amounts.freight,
        advance_paise: amounts.advance,
        valid_until: new Date(Date.now() + days * 86_400_000).toISOString(),
      })
      form.reset()
      setPrice(null)
      onDone('quote.draftFlash')
    })
  }
  const field = (name: string, label: Key, control?: { value: string; onChange: (v: string) => void }) => (
    <label className="field small">
      <span>{t(label)}</span>
      <input
        name={name}
        inputMode="decimal"
        {...(control ? { value: control.value, onChange: (e: React.ChangeEvent<HTMLInputElement>) => control.onChange(e.target.value) } : {})}
        aria-invalid={!!errors[name]} aria-describedby={errors[name] ? `${name}-err` : undefined} />
      {errors[name] && (
        <small id={`${name}-err`} className="field-error">
          {errors[name]}
        </small>
      )}
    </label>
  )
  return (
    <section className="quote-form" aria-labelledby="qf-title">
      <h2 id="qf-title">{t(rfq.quotes.length > 0 ? 'quote.formAgain' : 'quote.form')}</h2>
      <p className="hint">{t('quote.formLead', { n: rfq.quantity, unit })}</p>
      <form className="stack-form" onSubmit={onSubmit} noValidate>
        <div className="filter-row">
          {field('unit_price', 'quote.unitPrice', { value: price ?? listPrice, onChange: setPrice })}
          {field('discount', 'quote.discount')}
          {field('freight', 'quote.freight')}
          {field('advance', 'quote.advance')}
          <label className="field small">
            <span>{t('quote.validFor')}</span>
            <select name="valid_days" defaultValue="3">
              {VALID_DAYS.map((d) => (
                <option key={d} value={d}>
                  {t('product.days', { n: d })}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="note">{t('quote.taxNote')}</p>
        {submit.error && <ErrorState error={submit.error} />}
        <div className="form-actions">
          <button type="submit" className="btn primary" aria-disabled={submit.busy}>
            {submit.busy ? t('state.sending') : t('quote.saveDraft')}
          </button>
        </div>
      </form>
    </section>
  )
}

function SendDraft({ quote: q, onChange }: { quote: Quote; onChange: (k: Key | null) => void }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const submit = useSubmit()
  const send = () =>
    submit.run(async () => {
      try {
        await post(`/orgs/${orgId}/quotes/${q.id}/send`)
        onChange('quote.sentFlash')
      } catch (e) {
        if (e instanceof ApiError && e.code === 'quote_not_sendable') return onChange('quote.notSendable')
        throw e
      }
    })
  return (
    <>
      <p className="note">{t('quote.draftNote')}</p>
      {submit.error && <ErrorState error={submit.error} />}
      <div className="form-actions">
        <button type="button" className="btn primary" onClick={send} aria-disabled={submit.busy}>
          {submit.busy ? t('state.sending') : t('quote.send')}
        </button>
      </div>
    </>
  )
}

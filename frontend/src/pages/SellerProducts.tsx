import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError, api, post, useApi, type Product } from '../api.ts'
import { addCity } from '../cities.ts'
import { productName, useDate, useLang, type Key } from '../i18n.tsx'
import { can } from '../nav.ts'
import { toPaise } from '../rupees.ts'
import { useSession } from '../session.tsx'
import { Empty, ErrorState, Loading, Money, PageHead } from '../ui.tsx'
import { Fact, useSubmit } from './Trade.tsx'

// Seller's own product record (SPEC.md 6.4); differs from the public catalog shape.
export type SellerProduct = Omit<Product, 'seller'> & { status: 'active' | 'inactive'; version: number }

export function SellerProducts() {
  const { t, lang } = useLang()
  const { me, orgId } = useSession()
  const { data, error, loading, retry } = useApi<SellerProduct[]>(`/orgs/${orgId}/products`)
  return (
    <>
      <PageHead title={t('nav.myProducts')} lead={t('sp.lead')} />
      {can(me!, orgId, 'sell') ? (
        <Link to="/my-products/new" className="btn primary">
          {t('sp.add')}
        </Link>
      ) : (
        <p className="note">{t('perm.viewOnly')}</p>
      )}
      {error && <ErrorState error={error} onRetry={retry} />}
      {loading && <Loading />}
      {data && !loading && !error &&
        (data.length === 0 ? (
          <Empty title={t('sp.emptyTitle')} text={t('sp.empty')} />
        ) : (
          <ul className="rows">
            {data.map((p) => (
              <li key={p.id}>
                <Link to={`/my-products/${p.id}`} className="row-card">
                  <span className="row-main">
                    <strong>{productName(lang, p)}</strong>
                    <span>
                      {p.sku} · <Money paise={p.price_paise} /> {t('product.per', { unit: t(`unit.${p.unit}`) })}
                    </span>
                    <small>
                      {t('product.stock')} {p.available_qty}
                    </small>
                  </span>
                  <span className={`status status-${p.status === 'active' ? 'confirmed' : 'cancelled'}`}>{t(`sp.${p.status}`)}</span>
                </Link>
              </li>
            ))}
          </ul>
        ))}
    </>
  )
}

/** Reads the product form into the API body; returns field errors instead when input is invalid. */
function readForm(form: HTMLFormElement, t: (k: Key) => string, cities: string[]) {
  const f = new FormData(form)
  const text = (k: string) => String(f.get(k) ?? '').trim()
  const int = (k: string) => (/^\d+$/.test(text(k)) ? Number(text(k)) : NaN)
  const errors: Record<string, string> = {}
  const body = {
    sku: text('sku'),
    name: text('name'),
    name_te: text('name_te') || null,
    brand: text('brand'),
    model: text('model'),
    rating_amps: int('rating_amps'),
    voltage_v: int('voltage_v'),
    ways: Number(text('ways')),
    unit: text('unit'),
    pack_size: text('unit') === 'piece' ? 1 : int('pack_size'),
    moq: int('moq'),
    price_paise: toPaise(text('price')),
    lead_time_days: int('lead_time_days'),
    delivery_cities: cities,
  }
  for (const k of ['sku', 'name', 'brand', 'model'] as const) if (!body[k]) errors[k] = t('sp.required')
  for (const k of ['rating_amps', 'voltage_v', 'pack_size', 'moq'] as const) if (!(body[k] >= 1)) errors[k] = t('sp.wholeNumber')
  if (!(body.lead_time_days >= 0)) errors.lead_time_days = t('sp.wholeNumber')
  if (!body.price_paise) errors.price = t('quote.amountError')
  return { body, errors }
}

function ProductForm({ product, onSubmit, onInvalid, busy, submitLabel }: { product?: SellerProduct; onSubmit: (body: object) => void; onInvalid: () => void; busy: boolean; submitLabel: Key }) {
  const { t } = useLang()
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [unit, setUnit] = useState(product?.unit ?? 'box')
  const [cities, setCities] = useState(product?.delivery_cities ?? [])
  const [cityText, setCityText] = useState('')
  const [cityError, setCityError] = useState('')
  const cityInput = useRef<HTMLInputElement>(null)
  const add = () => {
    const r = addCity(cities, cityText)
    if (r.error) return setCityError(t(`sp.city.${r.error}`)), false
    setCities(r.list)
    setCityText('')
    setCityError('')
    return r.list
  }
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    // A city typed but not yet added is kept rather than silently dropped.
    const list = cityText.trim() ? add() : cities
    if (!list) return onInvalid()
    const { body, errors } = readForm(e.currentTarget, t, list)
    setErrors(errors)
    // An earlier server error no longer applies once the form shows its own field errors.
    if (Object.keys(errors).length) onInvalid()
    else onSubmit(body)
  }
  const field = (name: string, label: Key, value: string | number = '', extra: object = {}) => (
    <label className="field small">
      <span>{t(label)}</span>
      <input name={name} defaultValue={value} aria-invalid={!!errors[name]} aria-describedby={errors[name] ? `${name}-err` : undefined} {...extra} />
      {errors[name] && (
        <small id={`${name}-err`} className="field-error">
          {errors[name]}
        </small>
      )}
    </label>
  )
  const p = product
  return (
    <form className="stack-form wide" onSubmit={submit} noValidate>
      <div className="filter-row">
        {field('name', 'sp.name', p?.name, { maxLength: 200 })}
        {field('name_te', 'sp.nameTe', p?.name_te ?? '', { maxLength: 200, lang: 'te' })}
      </div>
      <div className="filter-row">
        {field('sku', 'sp.sku', p?.sku, { maxLength: 64 })}
        {field('brand', 'sp.brand', p?.brand, { maxLength: 80 })}
        {field('model', 'sp.model', p?.model, { maxLength: 80 })}
      </div>
      <div className="filter-row">
        {field('rating_amps', 'sp.amps', p?.rating_amps, { inputMode: 'numeric' })}
        {field('voltage_v', 'sp.volts', p?.voltage_v ?? 240, { inputMode: 'numeric' })}
        <label className="field small">
          <span>{t('products.ways')}</span>
          <select name="ways" defaultValue={p?.ways ?? 1}>
            <option value="1">{t('products.oneWay')}</option>
            <option value="2">{t('products.twoWay')}</option>
          </select>
        </label>
      </div>
      <div className="filter-row">
        <label className="field small">
          <span>{t('sp.unit')}</span>
          <select name="unit" value={unit} onChange={(e) => setUnit(e.target.value as 'piece' | 'box')}>
            <option value="box">{t('unit.box')}</option>
            <option value="piece">{t('unit.piece')}</option>
          </select>
        </label>
        {unit === 'box' && field('pack_size', 'sp.pack', p?.pack_size ?? 10, { inputMode: 'numeric' })}
        {field('moq', 'product.moq', p?.moq ?? 1, { inputMode: 'numeric' })}
        {field('price', 'sp.price', p ? (p.price_paise / 100).toFixed(2) : '', { inputMode: 'decimal' })}
        {field('lead_time_days', 'sp.lead', p?.lead_time_days ?? 2, { inputMode: 'numeric' })}
      </div>
      <fieldset className="cities">
        <legend>{t('sp.cities')}</legend>
        {cities.length > 0 && (
          <ul className="chips">
            {cities.map((c) => (
              <li key={c}>
                {c}
                <button type="button" className="chip-remove" aria-label={t('sp.city.remove', { city: c })} onClick={() => (setCities(cities.filter((x) => x !== c)), cityInput.current?.focus())}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="filter-actions">
          <label className="field small">
            <span>{t('sp.city.add')}</span>
            <input
              ref={cityInput}
              value={cityText}
              maxLength={120}
              aria-invalid={!!cityError}
              aria-describedby={cityError ? 'city-err' : undefined}
              onChange={(e) => setCityText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
            />
            {cityError && (
              <small id="city-err" className="field-error">
                {cityError}
              </small>
            )}
          </label>
          <button type="button" className="btn" onClick={add}>
            {t('sp.city.addButton')}
          </button>
        </div>
      </fieldset>
      <div className="form-actions">
        <button type="submit" className="btn primary" aria-disabled={busy}>
          {busy ? t('state.sending') : t(submitLabel)}
        </button>
      </div>
    </form>
  )
}

export function NewProduct() {
  const { t } = useLang()
  const { me, orgId } = useSession()
  const navigate = useNavigate()
  const submit = useSubmit()
  const back = (
    <Link to="/my-products" className="back">
      ← {t('nav.myProducts')}
    </Link>
  )
  if (!can(me!, orgId, 'sell')) return (<><PageHead title={t('sp.add')}>{back}</PageHead><Empty title={t('perm.title')} text={t('sp.perm')} /></>)
  return (
    <>
      <PageHead title={t('sp.add')} lead={t('sp.addLead')}>
        {back}
      </PageHead>
      {submit.error && <ErrorState error={submit.error} />}
      <ProductForm
        busy={submit.busy}
        submitLabel="sp.create"
        onInvalid={() => submit.setError(null)}
        onSubmit={(body) =>
          submit.run(async () => {
            try {
              const p = await post<SellerProduct>(`/orgs/${orgId}/products`, { ...body, status: 'active' })
              navigate(`/my-products/${p.id}`, { state: { flash: 'sp.created' } })
            } catch (e) {
              throw e instanceof ApiError && e.code === 'conflict' ? new ApiError(409, 'conflict', t('sp.skuTaken')) : e
            }
          })
        }
      />
    </>
  )
}

export function SellerProductView() {
  const { id } = useParams()
  const { t, lang } = useLang()
  const { me, orgId } = useSession()
  const editor = can(me!, orgId, 'sell')
  const { data: p, error, loading, retry } = useApi<SellerProduct>(`/orgs/${orgId}/products/${encodeURIComponent(id!)}`)
  const created = (useLocation().state as { flash?: Key } | null)?.flash
  const [flash, setFlash] = useState<string | null>(created ? t(created) : null)
  const submit = useSubmit()
  const back = (
    <Link to="/my-products" className="back">
      ← {t('nav.myProducts')}
    </Link>
  )
  if (error) return (<><PageHead title={t('nav.myProducts')}>{back}</PageHead><ErrorState error={error} onRetry={retry} /></>)
  if (loading || !p || p.id !== id) return (<><PageHead title={t('nav.myProducts')}>{back}</PageHead><Loading /></>)

  const reload = (message: string) => {
    setFlash(message)
    retry()
  }
  // Every edit carries the version that was loaded; a newer version on the server means someone else changed it first.
  const patch = (body: object, done: Key) =>
    submit.run(async () => {
      try {
        await api(`/orgs/${orgId}/products/${p.id}`, { method: 'PATCH', body: JSON.stringify({ ...body, version: p.version }) })
        reload(t(done))
      } catch (e) {
        if (e instanceof ApiError && e.code === 'version_conflict') return reload(t('sp.conflict'))
        throw e instanceof ApiError && e.code === 'conflict' ? new ApiError(409, 'conflict', t('sp.skuTaken')) : e
      }
    })
  return (
    <>
      <PageHead title={productName(lang, p)} lead={`${p.sku} · ${t(`sp.${p.status}`)}`}>
        {back}
      </PageHead>
      {flash && (
        <p className="flash" role="status">
          {flash}
        </p>
      )}
      <dl className="facts">
        <Fact label={t('product.stock')} value={`${p.available_qty} × ${t(`unit.${p.unit}`)}`} />
        <Fact label={t('sp.statusLabel')} value={t(`sp.${p.status}`)} />
        <Fact label={t('sp.price')} value={<Money paise={p.price_paise} />} />
        <Fact label={t('sp.version')} value={String(p.version)} />
      </dl>
      {submit.error && <ErrorState error={submit.error} />}
      {editor ? (
        <>
          <section aria-labelledby="stock-title" className="quote-form">
            <h2 id="stock-title">{t('sp.stockTitle')}</h2>
            <StockAdjust product={p} onDone={reload} />
          </section>
          <section aria-labelledby="history-title" className="quote-form">
            <h2 id="history-title">{t('sp.history')}</h2>
            {/* key: another organization, product or version starts the history again from the newest page, dropping older pages */}
            <StockHistory key={`${orgId}:${p.id}:${p.version}`} productId={p.id} unit={t(`unit.${p.unit}`)} />
          </section>
          <section aria-labelledby="status-title" className="quote-form">
            <h2 id="status-title">{t('sp.statusLabel')}</h2>
            <p className="hint">{t(p.status === 'active' ? 'sp.activeHint' : 'sp.inactiveHint')}</p>
            <div className="form-actions">
              <button type="button" className="btn" aria-disabled={submit.busy} onClick={() => patch({ status: p.status === 'active' ? 'inactive' : 'active' }, 'sp.statusSaved')}>
                {t(p.status === 'active' ? 'sp.deactivate' : 'sp.activate')}
              </button>
            </div>
          </section>
          <section aria-labelledby="edit-title" className="quote-form">
            <h2 id="edit-title">{t('sp.editTitle')}</h2>
            {/* key: after a save or a version conflict the form shows the server's latest values */}
            <ProductForm key={p.version} product={p} busy={submit.busy} submitLabel="sp.save" onInvalid={() => submit.setError(null)} onSubmit={(body) => patch(body, 'sp.saved')} />
          </section>
        </>
      ) : (
        <p className="note">{t('perm.viewOnly')}</p>
      )}
    </>
  )
}

function StockAdjust({ product: p, onDone }: { product: SellerProduct; onDone: (message: string) => void }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const submit = useSubmit()
  const [draft, setDraft] = useState<{ delta: number; reason: string; note: string | null; key: string } | null>(null)
  const [qtyError, setQtyError] = useState('')
  // What was typed, so Back from the review returns to the same values instead of an empty form.
  const [typed, setTyped] = useState({ direction: 'add', qty: '', reason: 'restock', note: '' })
  const reviewText = useRef<HTMLParagraphElement>(null)
  const nextButton = useRef<HTMLButtonElement>(null)
  const wasOpen = useRef(false)
  useEffect(() => {
    // Focus moves only when the review opens or closes, not on busy/error re-renders.
    if (draft) reviewText.current?.focus()
    else if (wasOpen.current) nextButton.current?.focus()
    wasOpen.current = !!draft
  }, [draft])

  const review = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const values = { direction: String(f.get('direction')), qty: String(f.get('qty')).trim(), reason: String(f.get('reason')), note: String(f.get('note')) }
    setTyped(values)
    const qty = values.qty
    // The API accepts changes of at most 1,000,000 units (SPEC 6.4 StockIn).
    if (!/^[1-9]\d{0,6}$/.test(qty) || Number(qty) > 1_000_000) return setQtyError(t('sp.qtyRange'))
    setQtyError('')
    const delta = Number(qty) * (f.get('direction') === 'remove' ? -1 : 1)
    // One key per reviewed adjustment, reused on retry, so a lost response cannot apply it twice.
    setDraft({ delta, reason: String(f.get('reason')), note: String(f.get('note')).trim() || null, key: crypto.randomUUID() })
  }
  const confirm = () =>
    draft &&
    submit.run(async () => {
      try {
        const m = await post<{ resulting_qty: number }>(`/orgs/${orgId}/products/${p.id}/stock-adjustments`, { delta: draft.delta, reason: draft.reason, note: draft.note }, { 'Idempotency-Key': draft.key })
        setDraft(null)
        onDone(t('sp.stockSaved', { n: m.resulting_qty }))
      } catch (e) {
        if (e instanceof ApiError && (e.code === 'insufficient_stock' || e.code === 'idempotency_key_reused')) {
          setDraft(null)
          return onDone(t(e.code === 'insufficient_stock' ? 'sp.insufficient' : 'sp.keyReused'))
        }
        throw e
      }
    })

  if (draft)
    return (
      <div className="review" role="group" aria-labelledby="stock-review">
        <p id="stock-review" tabIndex={-1} ref={reviewText}>
          {t('sp.stockReview', { from: p.available_qty, to: p.available_qty + draft.delta, reason: t(`sp.reason.${draft.reason}` as Key) })}
        </p>
        {submit.error && <ErrorState error={submit.error} />}
        <div className="form-actions">
          <button type="button" className="btn primary" onClick={confirm} aria-disabled={submit.busy}>
            {submit.busy ? t('state.sending') : t('sp.stockConfirm')}
          </button>
          <button type="button" className="btn ghost" onClick={() => !submit.busy && setDraft(null)} aria-disabled={submit.busy}>
            {t('confirm.back')}
          </button>
        </div>
      </div>
    )
  return (
    <form className="stack-form wide" onSubmit={review} noValidate>
      <div className="filter-row">
        <label className="field small">
          <span>{t('sp.direction')}</span>
          <select name="direction" defaultValue={typed.direction}>
            <option value="add">{t('sp.add_')}</option>
            <option value="remove">{t('sp.remove')}</option>
          </select>
        </label>
        <label className="field small">
          <span>{t('sp.qty', { unit: t(`unit.${p.unit}`) })}</span>
          <input name="qty" inputMode="numeric" defaultValue={typed.qty} aria-invalid={!!qtyError} aria-describedby={qtyError ? 'qty-err' : undefined} />
          {qtyError && (
            <small id="qty-err" className="field-error">
              {qtyError}
            </small>
          )}
        </label>
        <label className="field small">
          <span>{t('sp.reason')}</span>
          <select name="reason" defaultValue={typed.reason}>
            {['restock', 'correction', 'damage'].map((r) => (
              <option key={r} value={r}>
                {t(`sp.reason.${r}` as Key)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('sp.note')}</span>
          <input name="note" maxLength={200} defaultValue={typed.note} />
        </label>
      </div>
      <div className="form-actions">
        <button type="submit" className="btn primary" ref={nextButton}>
          {t('sp.stockNext')}
        </button>
      </div>
    </form>
  )
}

type HistoryItem = { id: string; delta: number; reason: string; note: string | null; resulting_qty: number; created_at: string; order_id: string | null; actor_name: string | null }
type HistoryPage = { items: HistoryItem[]; next_before: string | null }

function StockHistory({ productId, unit }: { productId: string; unit: string }) {
  const { t } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const base = `/orgs/${orgId}/products/${productId}/stock-movements?limit=10`
  const first = useApi<HistoryPage>(base)
  const [older, setOlder] = useState<HistoryPage[]>([])
  const more = useSubmit()
  if (first.error) return <ErrorState error={first.error} onRetry={first.retry} />
  if (first.loading || !first.data) return <Loading />
  const pages = [first.data, ...older]
  const items = pages.flatMap((p) => p.items)
  const cursor = pages.at(-1)!.next_before
  if (items.length === 0) return <p className="note">{t('sp.historyEmpty')}</p>
  const who = (m: HistoryItem) =>
    m.order_id ? (
      <Link to={`/orders/${m.order_id}`}>{t(m.reason === 'order_cancel' ? 'sp.byCancel' : 'sp.byOrder')}</Link>
    ) : (
      (m.actor_name ?? t('sp.bySystem'))
    )
  return (
    <>
      <ul className="rows history">
        {items.map((m) => (
          <li key={m.id} className="row-card">
            <span className="row-main">
              <strong>
                {m.delta > 0 ? '+' : '−'}
                {Math.abs(m.delta)} {unit} · {t(`sp.reason.${m.reason}` as Key)}
              </strong>
              <span>
                {t('sp.historyAfter', { n: m.resulting_qty })} · {who(m)}
              </span>
              <small>
                {date(m.created_at)}
                {m.note && ` · ${m.note}`}
              </small>
            </span>
          </li>
        ))}
      </ul>
      {more.error && <ErrorState error={more.error} />}
      {cursor && (
        <button
          type="button"
          className="btn more"
          aria-disabled={more.busy}
          onClick={() => more.run(async () => setOlder([...older, await api<HistoryPage>(`${base}&before=${cursor}`)]))}
        >
          {more.busy ? t('state.loading') : t('sp.historyMore')}
        </button>
      )}
    </>
  )
}

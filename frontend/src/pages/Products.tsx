import { useEffect, useRef } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router'
import { useApi, type CatalogPage, type Product } from '../api.ts'
import { useLang } from '../i18n.tsx'
import { can } from '../nav.ts'
import { useSession } from '../session.tsx'
import { Empty, ErrorState, Loading, Money, PageHead } from '../ui.tsx'

const FILTERS = ['q', 'city', 'quantity', 'rating_amps', 'ways'] as const
const PAGE = 20

const verified = (status: string) => status === 'simulated_verified'

export function Products() {
  const { t } = useLang()
  const [params, setParams] = useSearchParams()
  const offset = Math.max(0, Math.floor(Number(params.get('offset'))) || 0)

  const query = new URLSearchParams()
  for (const k of FILTERS) if (params.get(k)) query.set(k, params.get(k)!)
  // One extra row tells us whether a next page exists without an empty last page.
  query.set('limit', String(PAGE + 1))
  query.set('offset', String(offset))
  const page = useApi<CatalogPage>(`/catalog/products?${query}`)
  const items = page.data?.items.slice(0, PAGE) ?? []
  const hasNext = (page.data?.items.length ?? 0) > PAGE

  // After Previous/Next, move focus to the result count so keyboard users are not left on a vanished button.
  const countRef = useRef<HTMLParagraphElement>(null)
  const paged = useRef(false)
  useEffect(() => {
    if (paged.current && page.data) {
      paged.current = false
      countRef.current?.focus()
    }
  }, [page.data])

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const next = new URLSearchParams()
    for (const [k, v] of new FormData(e.currentTarget)) if (String(v).trim()) next.set(k, String(v).trim())
    setParams(next)
  }
  const goTo = (next: number) => {
    paged.current = true
    setParams((p) => (next > 0 ? p.set('offset', String(next)) : p.delete('offset'), p))
  }

  return (
    <>
      <PageHead title={t('products.title')} lead={t('products.lead')} />
      {/* key resets the uncontrolled fields when the URL filters change (e.g. Clear or Back). */}
      <form className="filters" onSubmit={submit} key={params.toString()} role="search">
        <label className="field grow">
          <span>{t('products.words')}</span>
          <input name="q" type="search" maxLength={100} defaultValue={params.get('q') ?? ''} />
        </label>
        <div className="filter-actions">
          <button type="submit" className="btn primary">
            {t('products.search')}
          </button>
          {[...params.keys()].length > 0 && (
            <button type="button" className="btn ghost" onClick={() => setParams({})}>
              {t('products.clear')}
            </button>
          )}
        </div>
        <details className="more-filters" open={FILTERS.slice(1).some((k) => params.get(k))}>
          <summary>{t('products.moreFilters')}</summary>
          <div className="filter-row">
            <label className="field">
              <span>{t('products.city')}</span>
              <input name="city" maxLength={80} defaultValue={params.get('city') ?? ''} />
            </label>
            <label className="field small">
              <span>{t('products.quantity')}</span>
              <input name="quantity" type="number" min={1} inputMode="numeric" defaultValue={params.get('quantity') ?? ''} />
            </label>
            <label className="field small">
              <span>{t('products.amps')}</span>
              <input name="rating_amps" type="number" min={1} inputMode="numeric" defaultValue={params.get('rating_amps') ?? ''} />
            </label>
            <label className="field small">
              <span>{t('products.ways')}</span>
              <select name="ways" defaultValue={params.get('ways') ?? ''}>
                <option value="">{t('products.any')}</option>
                <option value="1">{t('products.oneWay')}</option>
                <option value="2">{t('products.twoWay')}</option>
              </select>
            </label>
          </div>
        </details>
      </form>

      {page.error && <ErrorState error={page.error} onRetry={page.retry} />}
      {page.loading && <Loading />}
      {!page.error && !page.loading && page.data && (
        <>
          <p className="count" role="status" tabIndex={-1} ref={countRef}>
            {items.length > 0
              ? t('products.range', { from: offset + 1, to: offset + items.length })
              : t('products.count', { n: 0 })}
          </p>
          {items.length === 0 ? (
            <Empty title={t('products.emptyTitle')} text={t('products.emptyLead')} />
          ) : (
            <ul className="cards">
              {items.map((p) => (
                <li key={p.id}>
                  <ProductCard product={p} search={params.toString()} />
                </li>
              ))}
            </ul>
          )}
          {(offset > 0 || hasNext) && (
            <nav className="pager" aria-label={t('products.pages')}>
              {offset > 0 && (
                <button type="button" className="btn" onClick={() => goTo(Math.max(0, offset - PAGE))}>
                  ← {t('products.prev')}
                </button>
              )}
              {hasNext && (
                <button type="button" className="btn" onClick={() => goTo(offset + PAGE)}>
                  {t('products.next')} →
                </button>
              )}
            </nav>
          )}
        </>
      )}
    </>
  )
}

function ProductCard({ product: p, search }: { product: Product; search: string }) {
  const { t, lang } = useLang()
  const [main, other] = lang === 'te' && p.name_te ? [p.name_te, p.name] : [p.name, p.name_te]
  return (
    <Link to={`/products/${p.id}`} state={{ search }} className="product-card">
      <span className="product-name">{main}</span>
      {other && <span className="product-alt">{other}</span>}
      <span className="product-price">
        <Money paise={p.price_paise} /> <small>{t('product.per', { unit: t(`unit.${p.unit}`) })}</small>
      </span>
      <span className="product-facts">
        {t('product.moq')} {p.moq} · {t('product.stock')} {p.available_qty}
      </span>
      <span className="product-seller">
        {p.seller.name} · {p.seller.city}
      </span>
    </Link>
  )
}

export function ProductDetail() {
  const { id } = useParams()
  const { t, lang } = useLang()
  const { me, orgId } = useSession()
  const back = (useLocation().state as { search?: string } | null)?.search
  const { data: p, error, loading, retry } = useApi<Product>(`/catalog/products/${encodeURIComponent(id!)}`)
  const backLink = (
    <Link to={`/products${back ? `?${back}` : ''}`} className="back">
      ← {t('product.back')}
    </Link>
  )
  if (error) return (<><PageHead title={t('error.title')}>{backLink}</PageHead><ErrorState error={error} onRetry={retry} /></>)
  if (loading || !p || p.id !== id) return (<><PageHead title={t('products.title')}>{backLink}</PageHead><Loading /></>)

  const [main, other] = lang === 'te' && p.name_te ? [p.name_te, p.name] : [p.name, p.name_te]
  const unit = t(`unit.${p.unit}`)
  return (
    <>
      <PageHead title={main} lead={other ?? undefined}>
        {backLink}
      </PageHead>
      <div className="detail">
        <section className="price-box" aria-label={t('product.price')}>
          <span className="eyebrow">{t('product.price')}</span>
          <span className="big">
            <Money paise={p.price_paise} />
          </span>
          <span>{t('product.per', { unit })}</span>
          {p.seller.id === orgId ? (
            <p className="note">{t('product.own')}</p>
          ) : can(me!, orgId, 'buy') ? (
            <Link to={`/products/${p.id}/request`} className="btn primary">
              {t('rfq.new')}
            </Link>
          ) : (
            <p className="note">{t('perm.buy')}</p>
          )}
        </section>
        <dl className="facts">
          <Fact label={t('product.moq')} value={`${p.moq} × ${unit}`} />
          <Fact label={t('product.stock')} value={`${p.available_qty} × ${unit}`} />
          <Fact label={t('product.pack')} value={p.unit === 'box' ? `${p.pack_size} / ${unit}` : `1 ${unit}`} />
          <Fact label={t('product.rating')} value={`${p.rating_amps} A · ${p.voltage_v} V · ${p.ways === 1 ? t('products.oneWay') : t('products.twoWay')}`} />
          <Fact label={t('product.lead')} value={t('product.days', { n: p.lead_time_days })} />
          <Fact label={t('product.cities')} value={p.delivery_cities.join(', ') || '—'} />
          <Fact label="SKU" value={`${p.sku} · ${p.brand}`} />
        </dl>
        <section className="seller-box" aria-labelledby="seller-title">
          <h2 id="seller-title">{t('product.seller')}</h2>
          <p className="seller-name">{p.seller.name}</p>
          <p>{p.seller.city}</p>
          <p className="tag">{t(verified(p.seller.verification_status) ? 'product.verified' : 'product.unverified')}</p>
        </section>
      </div>
    </>
  )
}

const Fact = ({ label, value }: { label: string; value: string }) => (
  <div className="fact">
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
)

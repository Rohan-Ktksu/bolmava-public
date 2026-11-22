import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useApi, type Report, type TradeTotals } from '../api.ts'
import { useDate, useLang, type Key } from '../i18n.tsx'
import { rangeError } from '../reports.ts'
import { useSession } from '../session.tsx'
import { ErrorState, Loading, Money, PageHead } from '../ui.tsx'
import { Fact, Status } from './Trade.tsx'

/** Organization report (SPEC.md 9.6). Every number comes from the API; the screen adds nothing up. */
export function Reports() {
  const { t, lang } = useLang()
  const { orgId } = useSession()
  const date = useDate()
  const [params, setParams] = useSearchParams()
  const from = params.get('from') ?? ''
  const to = params.get('to') ?? ''
  const invalid = rangeError(from, to)
  const query = from && to ? `?from=${from}&to=${to}` : '' // none: the API's current Asia/Kolkata month
  const report = useApi<Report>(orgId && !invalid ? `/orgs/${orgId}/reports/summary${query}` : null)
  const [formError, setFormError] = useState<Key | null>(null)
  const r = report.data
  const error = formError ?? invalid
  const day = (d: string) =>
    new Intl.DateTimeFormat(lang === 'te' ? 'te-IN' : 'en-IN', { dateStyle: 'medium', timeZone: 'Asia/Kolkata' }).format(new Date(`${d}T00:00:00+05:30`))

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const next = { from: String(f.get('from') ?? ''), to: String(f.get('to') ?? '') }
    const problem = rangeError(next.from, next.to)
    setFormError(problem)
    if (!problem) setParams(next.from ? next : {})
  }

  return (
    <>
      <PageHead title={t('nav.reports')} lead={t('rep.lead')} />
      {/* key: show the period the API actually used, including its default month */}
      <form className="filters" onSubmit={submit} key={`${params}:${r?.from_date}:${r?.to_date}`} noValidate>
        <label className="field">
          <span>{t('rep.from')}</span>
          <input name="from" type="date" defaultValue={from || r?.from_date} aria-invalid={!!error} aria-describedby={error ? 'rep-err' : undefined} />
        </label>
        <label className="field">
          <span>{t('rep.to')}</span>
          <input name="to" type="date" defaultValue={to || r?.to_date} aria-invalid={!!error} aria-describedby={error ? 'rep-err' : undefined} />
        </label>
        <div className="filter-actions">
          <button type="submit" className="btn primary">
            {t('rep.show')}
          </button>
          {query && (
            <button type="button" className="btn ghost" onClick={() => (setFormError(null), setParams({}))}>
              {t('rep.thisMonth')}
            </button>
          )}
        </div>
        {error && (
          <small id="rep-err" className="field-error" role="alert">
            {t(error)}
          </small>
        )}
      </form>

      {report.error && <ErrorState error={report.error} onRetry={report.retry} />}
      {report.loading && <Loading />}
      {r && !report.loading && !report.error && (
        <>
          <h2 id="rep-period">{t('rep.period', { from: day(r.from_date), to: day(r.to_date) })}</h2>
          <p className="note">{t('rep.simulated')}</p>
          {r.sales.orders + r.sales.cancelled_orders + r.purchases.orders + r.purchases.cancelled_orders === 0 && (
            <p className="flash" role="status">
              {t('rep.noOrders')}
            </p>
          )}
          <div className="report-sides">
            <Side side="sales" totals={r.sales} />
            <Side side="purchases" totals={r.purchases} />
          </div>

          <section aria-labelledby="rep-attention" className="report-attention">
            <h2 id="rep-attention">{t('rep.attention')}</h2>
            <dl className="facts">
              <Fact label={t('rep.openCases')} value={String(r.open_cases)} />
              <Fact label={t('rep.delayed')} value={String(r.delayed_orders_count)} />
            </dl>
            <p className="note">{t('rep.delayedRule')}</p>
            {r.delayed_orders.length > 0 && (
              <ul className="rows">
                {r.delayed_orders.map((o) => (
                  <li key={o.order_id}>
                    <Link to={`/orders/${o.order_id}`} className="row-card">
                      <span className="row-main">
                        <strong>{t(o.side === 'sales' ? 'rep.delayedSale' : 'rep.delayedPurchase')}</strong>
                        <small>{date(o.created_at)}</small>
                      </span>
                      <Status kind="fulfil" value={o.fulfillment_status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {r.delayed_orders_count > r.delayed_orders.length && (
              <p className="note">{t('rep.delayedMore', { shown: r.delayed_orders.length, total: r.delayed_orders_count })}</p>
            )}
          </section>
          <p className="note">{t('rep.notSales')}</p>
        </>
      )}
    </>
  )
}

function Side({ side, totals: s }: { side: 'sales' | 'purchases'; totals: TradeTotals }) {
  const { t } = useLang()
  const k = (name: string) => t(`rep.${side}.${name}` as Key)
  return (
    <section aria-labelledby={`rep-${side}`} className="report-side">
      <h2 id={`rep-${side}`}>{k('title')}</h2>
      <h3>{t('rep.inPeriod')}</h3>
      <dl className="facts">
        <Fact label={t('rep.orders')} value={String(s.orders)} />
        <Fact label={t('rep.value')} value={<Money paise={s.order_value_paise} />} />
        <Fact label={t('rep.cancelled')} value={String(s.cancelled_orders)} />
        <Fact label={k('received')} value={<Money paise={s.received_paise} />} />
      </dl>
      <h3>{t('rep.asOfNow')}</h3>
      <dl className="facts">
        <Fact label={k('outstanding')} value={<Money paise={s.outstanding_paise} />} />
        <Fact label={k('refund')} value={<Money paise={s.refund_due_paise} />} />
        <Fact label={t('rep.awaiting')} value={<Money paise={s.awaiting_approval_paise} />} />
        <Fact label={t('rep.approved')} value={<Money paise={s.approved_unrecorded_paise} />} />
      </dl>
    </section>
  )
}

import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { post, type Org } from '../api.ts'
import { useLang, type Key } from '../i18n.tsx'
import { useSession } from '../session.tsx'
import { ErrorState, PageHead } from '../ui.tsx'
import { VoiceButton } from '../VoiceButton.tsx'
import { useSubmit } from './Trade.tsx'

type Field = 'name' | 'city' | 'state'
const MAX: Record<Field, number> = { name: 160, city: 80, state: 80 }

/**
 * Register a business (demo step 1) for the signed-in person, who becomes its admin (SPEC.md 6.3, POST /orgs).
 * Each text field can be spoken. The new organization is fictional and simulated-unverified.
 */
export function RegisterBusiness() {
  const { t } = useLang()
  const { reloadMe } = useSession()
  const submit = useSubmit()
  const [values, setValues] = useState<Record<Field, string>>({ name: '', city: '', state: 'Andhra Pradesh' })
  const [sell, setSell] = useState(false)
  const [buy, setBuy] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<Field | 'kind', Key>>>({})
  const [created, setCreated] = useState<Org | null>(null)
  // One key per set of details, reused when the same details are retried, so a lost response never registers twice.
  const sendKey = useRef<{ body: string; key: string } | null>(null)

  const set = (f: Field, v: string) => setValues((x) => ({ ...x, [f]: v.slice(0, MAX[f]) }))
  const send = (e: React.FormEvent) => {
    e.preventDefault()
    const next: typeof errors = {}
    for (const f of ['name', 'city', 'state'] as const) if (!values[f].trim()) next[f] = 'reg.required'
    if (!sell && !buy) next.kind = 'reg.kindRequired'
    setErrors(next)
    if (Object.keys(next).length) return
    const body = { name: values.name.trim(), city: values.city.trim(), state: values.state.trim(), can_sell: sell, can_buy: buy }
    const text = JSON.stringify(body)
    if (sendKey.current?.body !== text) sendKey.current = { body: text, key: crypto.randomUUID() }
    const key = sendKey.current.key
    void submit.run(async () => {
      const org = await post<Org>('/orgs', body, { 'Idempotency-Key': key })
      await reloadMe(org.id) // the new business appears in the switcher and becomes the current one
      setCreated(org)
    })
  }

  if (created)
    return (
      <>
        <PageHead title={t('reg.title')} />
        <section className="callout" role="status" aria-labelledby="reg-done">
          <h2 id="reg-done">{t('reg.done', { name: created.name })}</h2>
          <p>{t('reg.doneLead')}</p>
        </section>
        <div className="form-actions">
          {created.can_sell && (
            <Link to="/my-products/new" className="btn primary">
              {t('reg.addProduct')}
            </Link>
          )}
          {created.can_buy && (
            <Link to="/products" className="btn">
              {t('reg.browse')}
            </Link>
          )}
        </div>
      </>
    )

  const field = (f: Field, label: Key) => (
    <div className="reg-field">
      <label className="field">
        <span>{t(label)}</span>
        <input
          name={f}
          value={values[f]}
          maxLength={MAX[f]}
          onChange={(e) => set(f, e.target.value)}
          aria-invalid={!!errors[f]}
          aria-describedby={errors[f] ? `${f}-err` : undefined}
        />
        {errors[f] && (
          <small id={`${f}-err`} className="field-error">
            {t(errors[f])}
          </small>
        )}
      </label>
      <VoiceButton compact label={t('reg.speak', { field: t(label) })} onText={(x) => set(f, x)} />
    </div>
  )

  return (
    <>
      <PageHead title={t('reg.title')} lead={t('reg.lead')} />
      <p className="note">{t('reg.fictional')}</p>
      <form className="quote-form" onSubmit={send} noValidate>
        {field('name', 'reg.name')}
        {field('city', 'reg.city')}
        {field('state', 'reg.state')}
        <fieldset className="choice" aria-describedby={errors.kind ? 'kind-err' : undefined}>
          <legend>{t('reg.kind')}</legend>
          <label className="check">
            <input type="checkbox" checked={sell} onChange={(e) => setSell(e.target.checked)} />
            {t('reg.sell')}
          </label>
          <label className="check">
            <input type="checkbox" checked={buy} onChange={(e) => setBuy(e.target.checked)} />
            {t('reg.buy')}
          </label>
          {errors.kind && (
            <small id="kind-err" className="field-error" role="alert">
              {t(errors.kind)}
            </small>
          )}
        </fieldset>
        <p className="note">{t('voice.note')}</p>
        {submit.error && <ErrorState error={submit.error} />}
        <div className="form-actions">
          <button type="submit" className="btn primary" aria-disabled={submit.busy}>
            {submit.busy ? t('state.sending') : t('reg.submit')}
          </button>
        </div>
      </form>
    </>
  )
}

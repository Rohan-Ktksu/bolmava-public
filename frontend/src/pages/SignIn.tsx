import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useApi, type ApiError, type LocalUser } from '../api.ts'
import { LanguageSwitch } from '../App.tsx'
import { useLang, type Key } from '../i18n.tsx'
import { useSession } from '../session.tsx'
import { ErrorState, Loading } from '../ui.tsx'

/** Who each fictional demo person is (seed data, backend/app/seed.py), so a visitor knows whom to pick. */
const PEOPLE: Record<string, { group: Key; role: Key }> = {
  'ravi.seller@example.test': { group: 'front.group.seller', role: 'front.role.ravi' },
  'anitha.catalog@example.test': { group: 'front.group.seller', role: 'front.role.anitha' },
  'lakshmi.admin@example.test': { group: 'front.group.buyer', role: 'front.role.lakshmi' },
  'suresh.buyer@example.test': { group: 'front.group.buyer', role: 'front.role.suresh' },
  'meena.viewer@example.test': { group: 'front.group.buyer', role: 'front.role.meena' },
  'kiran.retail@example.test': { group: 'front.group.shop', role: 'front.role.kiran' },
  'sanjay.support@example.test': { group: 'front.group.support', role: 'front.role.support' },
  'vani.support@example.test': { group: 'front.group.support', role: 'front.role.support' },
  'farah.finance@example.test': { group: 'front.group.finance', role: 'front.role.finance' },
  'arjun.finance@example.test': { group: 'front.group.finance', role: 'front.role.finance' },
}
const GROUPS: Key[] = ['front.group.seller', 'front.group.buyer', 'front.group.shop', 'front.group.support', 'front.group.finance', 'front.group.other']
const FEATURES: [Key, Key][] = [
  ['front.f.assistant', 'front.f.assistantText'],
  ['front.f.trade', 'front.f.tradeText'],
  ['front.f.delivery', 'front.f.deliveryText'],
  ['front.f.support', 'front.f.supportText'],
  ['front.f.money', 'front.f.moneyText'],
  ['front.f.reports', 'front.f.reportsText'],
]
const REGISTRAR = 'kiran.retail@example.test' // the demo person who registers a new business from the front page

/** Front page: what Bolmava is, how to try it, the fictional demo people by role, and registering a business. */
export function SignIn() {
  const { t } = useLang()
  const { signIn } = useSession()
  const navigate = useNavigate()
  const users = useApi<LocalUser[]>('/auth/local/users')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const choose = async (email: string, then?: string) => {
    setBusy(email)
    setError(null)
    try {
      if (then) navigate(then) // the shell opens this page once signed in
      await signIn(email)
    } catch (e) {
      setError(e as ApiError)
      setBusy(null)
    }
  }
  const groupOf = (email: string) => PEOPLE[email]?.group ?? 'front.group.other'

  return (
    <main id="main" className="signin">
      <div className="signin-top">
        <span className="brand">
          <img src="/favicon.svg" alt="" width="32" height="32" /> Bolmava
        </span>
        <LanguageSwitch />
      </div>

      <header className="front-hero">
        <h1 id="page-title" tabIndex={-1}>
          {t('front.title')}
        </h1>
        <p className="lead">{t('front.lead')}</p>
        <p className="front-badge">{t('front.beta')}</p>
      </header>

      <section aria-labelledby="front-features">
        <h2 id="front-features">{t('front.featuresTitle')}</h2>
        <ul className="front-features">
          {FEATURES.map(([title, text]) => (
            <li key={title}>
              <strong>{t(title)}</strong>
              <span>{t(text)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="front-how">
        <h2 id="front-how">{t('front.howTitle')}</h2>
        <ol className="front-steps">
          <li>{t('front.how1')}</li>
          <li>{t('front.how2')}</li>
          <li>{t('front.how3')}</li>
        </ol>
      </section>

      <section aria-labelledby="people-title">
        <h2 id="people-title">{t('signin.title')}</h2>
        <p>{t('signin.lead')}</p>
        {error && <ErrorState error={error} />}
        {users.loading && <Loading />}
        {users.error && <ErrorState error={users.error} onRetry={users.retry} />}
        {users.data &&
          GROUPS.filter((g) => users.data!.some((u) => groupOf(u.email) === g)).map((g) => (
            <div key={g} className="people-group">
              <h3>{t(g)}</h3>
              <ul className="people">
                {users.data!
                  .filter((u) => groupOf(u.email) === g)
                  .map((u) => (
                    <li key={u.email}>
                      <button type="button" className="person" disabled={busy !== null} onClick={() => choose(u.email)}>
                        <span className="person-name">{u.display_name}</span>
                        {PEOPLE[u.email] && <span className="person-role">{t(PEOPLE[u.email].role)}</span>}
                        <span className="person-email">{u.email}</span>
                        <span className="person-go">{busy === u.email ? t('state.loading') : t('signin.as')}</span>
                      </button>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
      </section>

      <section className="callout front-register" aria-labelledby="front-register">
        <h2 id="front-register">{t('front.registerTitle')}</h2>
        <p>{t('front.registerText')}</p>
        <button type="button" className="btn primary" disabled={busy !== null} onClick={() => choose(REGISTRAR, '/register-business')}>
          {busy === REGISTRAR ? t('state.loading') : t('front.registerButton')}
        </button>
      </section>

      <p className="note">{t('signin.reload')}</p>
      <p className="note">{t('front.realAccounts')}</p>
    </main>
  )
}

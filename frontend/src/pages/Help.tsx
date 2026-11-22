import { Link, NavLink } from 'react-router'
import { LanguageSwitch, OrgSwitch } from '../App.tsx'
import { useLang, type Key } from '../i18n.tsx'
import { destinations } from '../nav.ts'
import { useSession } from '../session.tsx'
import { PageHead } from '../ui.tsx'

const STEPS: [Key, Key][] = [
  ['help.request', 'help.requestText'],
  ['help.quote', 'help.quoteText'],
  ['help.order', 'help.orderText'],
  ['help.payment', 'help.paymentText'],
  ['help.delivered', 'help.deliveredText'],
]

export function Help() {
  const { t } = useLang()
  const { orgId } = useSession()
  return (
    <>
      <PageHead title={t('help.title')} lead={t('help.lead')} />
      <ol className="steps">
        {STEPS.map(([title, text]) => (
          <li key={title}>
            <strong>{t(title)}</strong>
            <p>{t(text)}</p>
          </li>
        ))}
      </ol>
      <section className="callout" aria-labelledby="person-title">
        <h2 id="person-title">{t('help.person')}</h2>
        <p>{t('help.personText')}</p>
        {orgId && (
          <Link to="/conversation" className="btn">
            {t('nav.conversation')}
          </Link>
        )}
      </section>
      <p className="note">{t('help.reload')}</p>
    </>
  )
}

/** Phone-only page for destinations that do not fit the bottom bar, plus account controls. */
export function More() {
  const { t } = useLang()
  const { me, orgId, signOut } = useSession()
  return (
    <>
      <PageHead title={t('more')} />
      <div className="more-list">
        {destinations(me!, orgId).map((d) => (
          <NavLink key={d.path} to={d.path} end={d.path === '/'}>
            {t(d.label)}
          </NavLink>
        ))}
      </div>
      <div className="more-account">
        <OrgSwitch />
        <LanguageSwitch />
        <button type="button" className="btn" onClick={signOut}>
          {t('signOut')} — {me!.display_name}
        </button>
      </div>
    </>
  )
}

export function NotBuilt({ label }: { label: Key }) {
  const { t } = useLang()
  return (
    <>
      <PageHead title={t(label)} lead={t('notBuilt.lead')} />
      <div className="state empty" role="status">
        <strong>{t('notBuilt.title')}</strong>
        <Link to="/" className="btn">
          {t('notBuilt.home')}
        </Link>
      </div>
    </>
  )
}

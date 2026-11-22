import { Link } from 'react-router'
import { useLang } from '../i18n.tsx'
import { destinations } from '../nav.ts'
import { useSession } from '../session.tsx'
import { PageHead, TaskCard } from '../ui.tsx'

export function Home() {
  const { t } = useLang()
  const { me, orgId } = useSession()
  const org = me!.memberships.find((m) => m.organization.id === orgId)?.organization
  const later = destinations(me!, orgId).filter((d) => !d.ready)
  const support = me!.staff_roles.includes('support')
  const finance = me!.staff_roles.includes('finance')
  return (
    <>
      <PageHead title={t('home.lead')} lead={t('home.hello', { name: me!.display_name })} />
      <div className="tasks">
        {support && <TaskCard to="/support" title={t('nav.support')} text={t('home.support')} primary />}
        {finance && <TaskCard to="/finance" title={t('nav.finance')} text={t('home.finance')} primary />}
        <TaskCard to="/products" title={t('nav.products')} text={t('home.products')} primary={!support && !finance} />
        {org?.can_buy && <TaskCard to="/requests" title={t('nav.requests')} text={t('home.requests')} />}
        {org?.can_sell && <TaskCard to="/enquiries" title={t('nav.enquiries')} text={t('home.enquiries')} />}
        {org && <TaskCard to="/conversation" title={t('nav.conversation')} text={t('home.conversation')} />}
        <TaskCard to="/help" title={t('nav.help')} text={t('home.help')} />
      </div>
      {me!.memberships.length === 0 && !support && !finance && <p className="note">{t('home.staff')}</p>}
      {later.length > 0 && (
        <section className="later" aria-labelledby="later-title">
          <h2 id="later-title">{t('home.later')}</h2>
          <p>{t('home.laterLead')}</p>
          <ul>
            {later.map((d) => (
              <li key={d.path}>
                <Link to={d.path}>{t(d.label)}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

import { useEffect, useRef } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation } from 'react-router'
import { useLang, type Lang } from './i18n.tsx'
import { destinations } from './nav.ts'
import { Complaint, Complaints } from './pages/Complaints.tsx'
import { Conversation } from './pages/Conversation.tsx'
import { FinanceOrder, FinanceQueue } from './pages/Finance.tsx'
import { Help, More, NotBuilt } from './pages/Help.tsx'
import { Reports } from './pages/Reports.tsx'
import { Home } from './pages/Home.tsx'
import { OrderView, Orders } from './pages/Orders.tsx'
import { ProductDetail, Products } from './pages/Products.tsx'
import { NewProduct, SellerProductView, SellerProducts } from './pages/SellerProducts.tsx'
import { RegisterBusiness } from './pages/RegisterBusiness.tsx'
import { SignIn } from './pages/SignIn.tsx'
import { WhatsAppSim } from './pages/WhatsAppSim.tsx'
import { SupportCase, SupportHandoff, SupportQueue } from './pages/Support.tsx'
import { RequestQuote, RfqList, RfqView } from './pages/Trade.tsx'
import { useSession } from './session.tsx'

const PHONE_TABS = 4

export default function App() {
  const { me, orgId } = useSession()
  return (
    <>
      <a href="#main" className="skip">
        {useLang().t('skip')}
      </a>
      <DemoStrip />
      {me ? (
        <Shell>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/products" element={<Products />} />
            <Route path="/products/:id" element={<ProductDetail />} />
            <Route path="/products/:id/request" element={<RequestQuote />} />
            <Route path="/requests" element={<RfqList side="buyer" />} />
            <Route path="/requests/:id" element={<RfqView />} />
            <Route path="/enquiries" element={<RfqList side="seller" />} />
            <Route path="/enquiries/:id" element={<RfqView />} />
            <Route path="/my-products" element={<SellerProducts />} />
            <Route path="/my-products/new" element={<NewProduct />} />
            <Route path="/my-products/:id" element={<SellerProductView />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/orders/:id" element={<OrderView />} />
            <Route path="/conversation" element={<Conversation />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/complaints" element={<Complaints />} />
            <Route path="/complaints/:id" element={<Complaint />} />
            <Route path="/whatsapp-sim" element={<WhatsAppSim />} />
            <Route path="/register-business" element={<RegisterBusiness />} />
            <Route path="/support" element={<SupportQueue />} />
            <Route path="/finance" element={<FinanceQueue />} />
            <Route path="/finance/orders/:id" element={<FinanceOrder />} />
            <Route path="/support/cases/:id" element={<SupportCase />} />
            <Route path="/support/handoffs/:id" element={<SupportHandoff />} />
            <Route path="/help" element={<Help />} />
            <Route path="/more" element={<More />} />
            {destinations(me, orgId)
              .filter((d) => !d.ready)
              .map((d) => (
                <Route key={d.path} path={d.path} element={<NotBuilt label={d.label} />} />
              ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Shell>
      ) : (
        <SignIn />
      )}
    </>
  )
}

function DemoStrip() {
  return (
    <div className="demo-strip" role="note">
      {useLang().t('demoStrip')}
    </div>
  )
}

export function LanguageSwitch() {
  const { lang, setLang, t } = useLang()
  const opts: [Lang, string][] = [
    ['en', 'English'],
    ['te', 'తెలుగు'],
  ]
  return (
    <div className="lang" role="group" aria-label={t('language')}>
      {opts.map(([value, label]) => (
        <button key={value} type="button" lang={value} aria-pressed={lang === value} onClick={() => setLang(value)}>
          {label}
        </button>
      ))}
    </div>
  )
}

export function OrgSwitch() {
  const { me, orgId, setOrgId } = useSession()
  const { t } = useLang()
  if (!me) return null
  if (me.memberships.length === 0)
    return (
      <p className="org-static">
        <span className="org-label">{t('staffOnly')}</span>
        {me.staff_roles.map((r) => t(`role.${r}`)).join(', ')}
      </p>
    )
  return (
    <label className="org">
      <span className="org-label">{t('organization')}</span>
      <select value={orgId ?? ''} onChange={(e) => setOrgId(e.target.value)}>
        {me.memberships.map((m) => (
          <option key={m.organization.id} value={m.organization.id}>
            {m.organization.name} — {t(`role.${m.role}`)}
          </option>
        ))}
      </select>
    </label>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  const { me, orgId, signOut } = useSession()
  const { t } = useLang()
  const location = useLocation()
  const first = useRef(true)
  // Move focus to the new page title so keyboard and screen-reader users land on the content.
  useEffect(() => {
    if (first.current) return void (first.current = false)
    document.getElementById('page-title')?.focus()
  }, [location.pathname])

  const dests = destinations(me!, orgId)
  const tabs = dests.slice(0, PHONE_TABS)
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <img src="/favicon.svg" alt="" width="32" height="32" />
          <span>
            Bolmava <small>{t('brandTag')}</small>
          </span>
        </Link>
        <OrgSwitch />
        <div className="topbar-actions">
          <LanguageSwitch />
          <Link to="/help" className="btn ghost wide-only">
            {t('help')}
          </Link>
          <button type="button" className="btn ghost wide-only" onClick={signOut}>
            {t('signOut')}
          </button>
        </div>
      </header>
      <nav className="rail" aria-label={t('mainNav')}>
        <p className="who">
          {me!.display_name}
          <small>{me!.email}</small>
        </p>
        {dests.map((d) => (
          <NavLink key={d.path} to={d.path} end={d.path === '/'}>
            {t(d.label)}
          </NavLink>
        ))}
      </nav>
      <main id="main" className="content">
        {children}
      </main>
      <nav className="tabbar" aria-label={t('mainNav')}>
        {tabs.map((d) => (
          <NavLink key={d.path} to={d.path} end={d.path === '/'}>
            {t(d.label)}
          </NavLink>
        ))}
        <NavLink to="/more">{t('more')}</NavLink>
      </nav>
    </div>
  )
}

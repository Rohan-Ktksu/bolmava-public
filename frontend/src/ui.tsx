import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { ApiError } from './api.ts'
import { useLang } from './i18n.tsx'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })

/** Shows integer paise from the API as INR. Display only: no arithmetic beyond the unit shift. */
export const Money = ({ paise }: { paise: number }) => <span className="money">{inr.format(paise / 100)}</span>

export function PageHead({ title, lead, children }: { title: string; lead?: string; children?: ReactNode }) {
  return (
    <header className="page-head">
      {children}
      <h1 id="page-title" tabIndex={-1}>
        {title}
      </h1>
      {lead && <p className="lead">{lead}</p>}
    </header>
  )
}

export function TaskCard({ to, title, text, primary }: { to: string; title: string; text: string; primary?: boolean }) {
  return (
    <Link to={to} className={primary ? 'task-card primary' : 'task-card'}>
      <span className="task-title">{title}</span>
      <span className="task-text">{text}</span>
      <span aria-hidden="true" className="task-arrow">
        →
      </span>
    </Link>
  )
}

export function Loading() {
  const { t } = useLang()
  return (
    <div className="state" role="status">
      <span className="spinner" aria-hidden="true" />
      {t('state.loading')}
    </div>
  )
}

export function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="state empty" role="status">
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const { t } = useLang()
  // Prefer the API's own message (SPEC.md 6.1); fall back to plain words, never to invented data.
  const message =
    error.code === 'network' ? t('error.network') : error.status === 404 ? t('error.notFound') : error.message || t('error.generic')
  return (
    <div className="state error" role="alert">
      {/* Loads offer Try again; a failed save or action does not, and must not say "load". */}
      <strong>{t(onRetry ? 'error.title' : 'error.actionTitle')}</strong>
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          {t('state.retry')}
        </button>
      )}
    </div>
  )
}

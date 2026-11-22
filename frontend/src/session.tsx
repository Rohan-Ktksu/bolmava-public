import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setToken, setUnauthenticatedHandler, type Me } from './api.ts'
import { useLang } from './i18n.tsx'

type Ctx = {
  me: Me | null
  orgId: string | null
  setOrgId: (id: string) => void
  signIn: (email: string) => Promise<void>
  signOut: () => void
  /** Reload the person's organizations (after registering one) and optionally switch to `select`. */
  reloadMe: (select?: string) => Promise<void>
}
const SessionContext = createContext<Ctx>(null!)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [orgId, setOrgId] = useState<string | null>(null)
  const { chosen, setLang } = useLang()

  const signOut = () => {
    setToken(null)
    setMe(null)
    setOrgId(null)
  }
  useEffect(() => setUnauthenticatedHandler(signOut), [])

  const signIn = async (email: string) => {
    const { access_token } = await api<{ access_token: string }>('/auth/local/session', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
    setToken(access_token)
    try {
      const profile = await api<Me>('/me')
      setMe(profile)
      setOrgId(profile.memberships[0]?.organization.id ?? null)
      if (!chosen && (profile.preferred_language === 'te' || profile.preferred_language === 'en')) setLang(profile.preferred_language)
    } catch (e) {
      setToken(null)
      throw e
    }
  }

  const reloadMe = async (select?: string) => {
    const profile = await api<Me>('/me')
    setMe(profile)
    if (select) setOrgId(select)
  }

  return <SessionContext value={{ me, orgId, setOrgId, signIn, signOut, reloadMe }}>{children}</SessionContext>
}

export const useSession = () => useContext(SessionContext)

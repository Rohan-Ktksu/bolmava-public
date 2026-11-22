// The end-to-end suite rebuilds its database before every run. Refuse anything but a disposable local *_e2e database.
const LOCAL = new Set(['localhost', '127.0.0.1', '[::1]'])

export function e2eDatabaseUrl(env: NodeJS.ProcessEnv = process.env): string {
  const url = env.E2E_DATABASE_URL
  if (!url) throw new Error('Set E2E_DATABASE_URL to a disposable local PostgreSQL database whose name ends in _e2e.')
  for (const name of ['PGHOSTADDR', 'PGSERVICE']) if (env[name]) throw new Error(`Unset ${name}; it can redirect the database connection.`)
  const u = new URL(url.replace(/^postgresql\+psycopg:/, 'postgresql:'))
  const db = decodeURIComponent(u.pathname.slice(1))
  if (u.protocol !== 'postgresql:') throw new Error('E2E_DATABASE_URL must be a postgresql+psycopg:// URL.')
  if (u.search) throw new Error('E2E_DATABASE_URL may not carry query parameters.')
  if (!LOCAL.has(u.hostname) || !u.port) throw new Error(`E2E database must be on localhost with an explicit port, not ${u.host}.`)
  if (!db.endsWith('_e2e')) throw new Error(`E2E database name ${db} does not end with _e2e.`)
  return url
}

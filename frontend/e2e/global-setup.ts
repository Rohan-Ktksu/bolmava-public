import { execFileSync } from 'node:child_process'
import { backendEnv, python } from '../playwright.config.ts'

// Start every run from the same fictional seed: rebuild the guarded *_e2e database.
export default function globalSetup() {
  for (const args of [['-m', 'alembic', 'downgrade', 'base'], ['-m', 'alembic', 'upgrade', 'head'], ['-m', 'app.seed']])
    execFileSync(python, args, { cwd: '../backend', env: { ...process.env, ...backendEnv }, stdio: 'inherit' })
}

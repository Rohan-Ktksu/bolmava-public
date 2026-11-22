import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'
import { e2eDatabaseUrl } from './e2e/guard.ts'

// Real FastAPI + PostgreSQL + Vite; no mocked API. See docs/CI.md for local and GitHub runs.
// E2E_PYTHON: interpreter path relative to backend/ (for example .venv/Scripts/python.exe); CI uses python on PATH.
export const python = process.env.E2E_PYTHON ? resolve('../backend', process.env.E2E_PYTHON) : 'python'
export const backendEnv = {
  DATABASE_URL: e2eDatabaseUrl(),
  APP_ENV: 'local',
  AUTH_MODE: 'local',
  LOCAL_AUTH_SECRET: 'e2e-only-demo-signing-value',
}

// Trade screens arrive with F01a (PR #14); until they exist on the tested commit their spec is skipped, not failed.
const tradeBuilt = existsSync('src/pages/Trade.tsx')

export default defineConfig({
  testDir: 'e2e',
  testIgnore: tradeBuilt ? [] : ['**/trade.spec.ts'],
  globalSetup: './e2e/global-setup.ts',
  workers: 1, // one shared database
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }], ['junit', { outputFile: 'playwright-report/junit.xml' }]]
    : [['list']],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5173',
    locale: 'en-IN',
    timezoneId: 'Asia/Kolkata',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/health',
      env: { ...process.env, ...backendEnv } as Record<string, string>,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    { command: 'npm run dev -- --port 5173 --strictPort', url: 'http://localhost:5173', reuseExistingServer: false, timeout: 60_000 },
  ],
})

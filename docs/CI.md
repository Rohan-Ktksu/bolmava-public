# Automated testing (CI01)

Owner: Rohan-Ktksu. Added 31 October 2026. GitHub Actions on standard GitHub-hosted Ubuntu runners; fictional data and disposable databases only. Nothing here deploys, merges, or connects to a production or external database.

## Levels

| Level | Workflow | When it runs | What it checks | Typical time |
| --- | --- | --- | --- | --- |
| 1 | [.github/workflows/ci.yml](../.github/workflows/ci.yml) | Every pull request (each push), or manually through `manual.yml` | Backend: Python 3.13, PostgreSQL 16, pinned dependencies, full pytest suite, `reviews/*_regressions.py`, Alembic upgrade → downgrade base → upgrade → `alembic check`, seed twice. Frontend: Node 24, `npm ci`, `npm run lint` (errors fail, warnings counted in the summary), `npm run build`, `npm test`. | about 1.5 min (backend and frontend run in parallel) |
| 2 | [.github/workflows/e2e.yml](../.github/workflows/e2e.yml) | Pull requests carrying the `e2e` label (on labelling and on every later push), or manually through `manual.yml` | Playwright, Chromium only, against a real uvicorn + Vite + PostgreSQL 16 `_e2e` database rebuilt and seeded at the start of the run. No mocked API. | a few minutes |
| 3 | [.github/workflows/perf.yml](../.github/workflows/perf.yml) | Manual only | Locust benchmark against a local uvicorn on the runner and a disposable `_perf` database: catalog search, RFQ create and same-key retry, quote retrieval, order confirmation and same-key retry, concurrent stock adjustments. Reports p50/p95/p99, requests/s, failures and the runner hardware. | 1–6 min plus setup |

Browser tests (`frontend/e2e/`):

- `shell.spec.ts` (works on today's `main`): fictional sign-in and reload behaviour, organization switching and cross-organization isolation, product discovery, English/Telugu navigation, 360 px phone layout, keyboard basics.
- `trade.spec.ts` (F01a): RFQ creation with a lost response and retry, seller form input preservation with a delayed price and a failed save, quote sending, IST deadline in a New York browser, keyboard review and same-key order retry, stale quote and rejection, organization switch during an in-flight request. It runs automatically once `frontend/src/pages/Trade.tsx` exists on the tested commit (F01a, PR #14); before that Playwright skips the file instead of failing.

Failures keep the Playwright HTML report, screenshots and traces (`retain-on-failure`) as a 7-day artifact; open a trace with `npx playwright show-trace trace.zip`.

## Running from GitHub

- **Level 1** starts by itself on every pull request push. Its checks appear on the PR and on the head commit.
- **Level 2 on a pull request:** add the `e2e` label (PR page → Labels). It runs immediately and again on each push while the label stays. Remove the label to stop.
- **Manual run of levels 1–2 against a chosen commit:** Actions tab → **Manual test run (levels 1-2)** → **Run workflow** → enter `ref` (a branch such as `main`, a full commit SHA, or `refs/pull/14/head` for PR #14's current head) and choose `1 and 2`, `1` or `2` → Run. From a terminal: `gh workflow run manual.yml -f ref=refs/pull/14/head -f levels="1 and 2"`. It calls `ci.yml` and/or `e2e.yml`, then writes one commit status, `ci/manual run`, on the exact commit resolved from `ref`, linking back to the run, so the result shows next to that commit and on any PR containing it.
- **Level 3:** Actions tab → **CI level 3 (performance, manual)** → Run workflow → `ref`, users (1–50) and duration (10–300 s); or `gh workflow run perf.yml -f ref=main -f users=20 -f duration=60`. It writes its table to the run summary and uploads `perf-results` (CSV and HTML, 14 days).
- The commit-status job exists only in `manual.yml`, so pull-request runs list only real test jobs. A pull request without the `e2e` label still shows one skipped level 2 check per push, because GitHub cannot filter a trigger by label.
- GitHub only offers **Run workflow** for workflows that exist on the default branch, so manual runs become available after CI01 is merged. Pull-request triggers work from the CI01 branch already.
- Nothing merges automatically.

## Running locally (Windows PowerShell)

```powershell
# Backend (same as Level 1)
cd backend; $env:BOLMAVA_DESTRUCTIVE_TESTS = "1"; python -m pytest; python -m pytest ..\reviews\b03_regressions.py ..\reviews\b04_regressions.py ..\reviews\r03_regressions.py

# Browser tests: a separate local database whose name ends in _e2e (the suite erases and reseeds it)
psql -h localhost -U postgres -c "CREATE DATABASE bolmava_e2e OWNER bolmava"
cd frontend; npx playwright install chromium
$env:E2E_DATABASE_URL = "postgresql+psycopg://bolmava:bolmava@localhost:5432/bolmava_e2e"
$env:E2E_PYTHON = ".venv/Scripts/python.exe"   # interpreter path relative to backend/
npm run e2e                                      # starts uvicorn on 8000 and Vite on 5173 itself; both ports must be free

# Benchmark: Locust in its own virtual environment, API against a separate *_perf database
python -m venv ..\perfvenv; ..\perfvenv\Scripts\pip install -r backend\perf\requirements.txt
# start uvicorn with DATABASE_URL pointing at bolmava_perf (migrated and seeded), then:
..\perfvenv\Scripts\locust -f backend\perf\locustfile.py --headless -u 20 -r 5 -t 60s --host http://127.0.0.1:8000 --csv out\perf
python backend\perf\summary.py out\perf_stats.csv "20 users, 60 s"
```

## Security and cost controls

- Workflow token is read-only (`contents: read`). Only the small final job of a manual run gets `statuses: write`, to record the result on the tested commit. No repository secrets are used; the demo signing values in the workflows are throwaway strings for local fictional mode.
- `pull_request` is used, never `pull_request_target`, so pull-request code never runs with write tokens or secrets. Checkout does not persist credentials.
- Third-party actions are pinned to full commit SHAs (checkout v7.0.1, setup-python v7.0.0, setup-node v7.0.0, upload-artifact v7.0.2). Python, npm and Locust dependencies are exact pins; `npm ci` uses the lockfile.
- Databases live only in each job's PostgreSQL 16 service container on `localhost`. The backend tests keep their own guard (`BOLMAVA_DESTRUCTIVE_TESTS=1`, a local `_test` database distinct from the application database). The browser suite refuses any `E2E_DATABASE_URL` that is not on localhost with an explicit port, not named `*_e2e`, or carries query parameters, and refuses `PGHOSTADDR`/`PGSERVICE`. The benchmark refuses any target host other than localhost and creates its own `_perf` database.
- Manual inputs are passed through environment variables, not pasted into shell scripts; benchmark users and duration are range-checked.
- Every job has a timeout (3–20 min). `concurrency` cancels superseded PR runs. Artifacts are uploaded only on failure (Levels 1–2) with 7-day retention; benchmark results keep 14 days. Pip and npm caches are used; Playwright downloads Chromium only, and only in Level 2.

## Approximate consumption

Standard runners are free for public repositories. In a private copy, minutes count against the account's included GitHub Actions allowance (2,000 minutes a month on GitHub Free, 3,000 on Pro; standard Linux runners count at 1×). Level 1 uses about 3 runner-minutes per PR push (two jobs, each rounded up to a whole minute). Example month: 40 PR pushes at Level 1 (~120 min) plus 10 labelled Level 2 runs and 2 benchmarks stays well inside the allowance. No paid resources are created.

## Gaps not covered yet

- Docker Compose and clean-machine Windows setup (V00) are not exercised; CI uses Ubuntu with service containers.
- Browser tests use Chromium only (no Firefox/WebKit or real phones), and no screen-reader or zoom checks.
- Trade browser tests run in CI only after F01a (PR #14) is merged; they were verified locally against its code.
- Fulfillment, payments, support/finance, conversation and report screens are not built, so they have no browser tests.
- The benchmark is a single uvicorn worker on a shared 4-vCPU runner: compare runs with each other, not with production capacity.

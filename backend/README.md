# Bolmava backend

FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16. Contract: [../SPEC.md](../SPEC.md). Fictional organizations and simulated money only.

Pinned versions: Python 3.13, PostgreSQL 16, packages in `requirements.txt` (generated from `requirements.in`; dev/test tools in `requirements-dev.txt`).

## Windows setup (PowerShell)

Prerequisites:

- Python 3.13 from python.org (tick "Add python.exe to PATH"), checked with `py -3.13 --version`.
- PostgreSQL 16, either:
  - **Docker Desktop** with the WSL 2 backend (needs hardware virtualization enabled; free only for personal use, education, and small businesses, so check Docker's licence terms), or
  - the **EDB PostgreSQL 16 installer** for Windows (no Docker needed).
- Keep the project and database storage outside OneDrive-synced folders.

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env            # then set LOCAL_AUTH_SECRET to a long random string
```

Start PostgreSQL with Docker:

```powershell
docker compose up -d                   # creates database bolmava, plus bolmava_test owned by a separate test role
docker compose ps                      # wait until postgres is "healthy"
```

Or with the EDB installer, open "SQL Shell (psql)" as the `postgres` superuser and run:

```sql
CREATE ROLE bolmava LOGIN PASSWORD 'bolmava';
CREATE DATABASE bolmava OWNER bolmava;
CREATE ROLE bolmava_test LOGIN PASSWORD 'bolmava_test';
CREATE DATABASE bolmava_test OWNER bolmava_test;
REVOKE CONNECT ON DATABASE bolmava FROM PUBLIC;
```

Create the schema, load fictional data, and run the API:

```powershell
alembic upgrade head
python -m app.seed                     # safe to rerun
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for interactive API docs and http://localhost:8000/openapi.json for the contract the frontend generates types from.

Run the fictional backend journey against the running API (another terminal; uses only the Python standard library):

```powershell
python scripts/demo_journey.py                  # seller catalog -> assistant RFQ -> quote -> order -> simulated advance
                                                # -> fulfillment -> complaint + human handoff -> report
python scripts/demo_journey.py --report-only    # print saved-record report totals
```

Set `$env:BOLMAVA_API` if the API is not at `http://localhost:8000`. Each run adds new fictional records. This is an API script: it does not show that voice, WhatsApp, or a frontend work.

Back up and restore into a separate database, then compare report totals (PostgreSQL 16 client tools; `psql` as the `postgres` superuser for `CREATE DATABASE`):

```powershell
pg_dump -h localhost -U bolmava -Fc -f bolmava.dump bolmava       # keep dumps out of Git and OneDrive
psql -h localhost -U postgres -c "CREATE DATABASE bolmava_restore OWNER bolmava"
pg_restore -h localhost -U bolmava -d bolmava_restore --no-owner bolmava.dump
$env:DATABASE_URL = "postgresql+psycopg://bolmava:bolmava@localhost:5432/bolmava_restore"
uvicorn app.main:app --port 8001                                    # then, in another terminal:
$env:BOLMAVA_API = "http://localhost:8001"; python scripts/demo_journey.py --report-only
```

Run the tests. They erase and rebuild `bolmava_test` on every run, so they need an explicit opt-in:

```powershell
$env:BOLMAVA_DESTRUCTIVE_TESTS = "1"
python -m pytest
```

Before connecting, the tests refuse to run unless the opt-in is set and `TEST_DATABASE_URL` states its host, port, and database explicitly, names a database ending in `_test` on localhost, and is not where `DATABASE_URL` actually connects. The only query parameters allowed in `TEST_DATABASE_URL` are `sslmode`, `connect_timeout`, and `application_name`; the `PGHOSTADDR` and `PGSERVICE` environment variables must be unset. For a disposable database on another host (for example a CI service container), also set `TEST_DATABASE_ALLOWED_HOST` to that host name.

If you set up the databases before the R01 fixes (one `bolmava` role for both), run the `bolmava_test` lines of the SQL above as the `postgres` superuser, first running `DROP DATABASE bolmava_test;`.

On Linux/macOS, use `python3.13 -m venv .venv`, `source .venv/bin/activate`, and `cp` in place of `Copy-Item`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_ENV` | `local` | `local`, `test`, or `production`. |
| `AUTH_MODE` | `local` | `local` = fictional users without passwords. `cognito` is not implemented yet and refuses to start. `local` with `APP_ENV=production` refuses to start. |
| `DATABASE_URL` | local `bolmava` database | SQLAlchemy URL (`postgresql+psycopg://...`). |
| `TEST_DATABASE_URL` | `bolmava_test` role and database on localhost | Used only by tests; erased on every run. |
| `BOLMAVA_DESTRUCTIVE_TESTS` | unset | Must be `1` for tests to run. |
| `TEST_DATABASE_ALLOWED_HOST` | unset | Allows a non-local disposable test database host. |
| `LOCAL_AUTH_SECRET` | demo value | Signs local demo tokens. |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Existing backend default from the former frontend plan. F00 should use Vite's same-origin `/api` development proxy; set an explicit origin only for a direct cross-origin browser setup. |

## Using the API from the frontend

The planned React/Vite F00 app calls `/api` on its own origin; Vite proxies those requests to FastAPI at `http://localhost:8000` in local development. The F00 app in [../frontend](../frontend/README.md) implements this proxy. The local demo bearer token belongs only in memory. The API below is unchanged by the frontend planning update.

1. `GET /api/v1/auth/local/users` lists fictional demo users for a sign-in picker.
2. `POST /api/v1/auth/local/session` with `{"email": "..."}` returns `access_token`.
3. Send `Authorization: Bearer <access_token>` on every other call.
4. `GET /api/v1/me` returns the user's organizations and roles. Organization routes are `/api/v1/orgs/{org_id}/...`.
5. Errors always look like `{"error": {"code", "message", "details"}}`. Show `message` and branch on `code` (SPEC.md section 6.1).
6. Stock adjustments need an `Idempotency-Key` header. Generate one per user action (e.g. `crypto.randomUUID()`), and reuse it when retrying that same action.
7. Product edits must send the `version` you loaded. On `409 version_conflict`, reload and ask the user again.

Trade flow (B03; full contract in SPEC.md sections 5 and 6.6–6.7):

1. Buyer: `POST /api/v1/orgs/{buyer_org}/rfqs` with a discovery `product_id`, `quantity` (at least the product's `moq`), and `delivery_city`.
2. Seller: `POST /api/v1/orgs/{seller_org}/rfqs/{rfq_id}/quotes` creates a draft. The backend computes subtotal, 18% simulated tax, and total; `valid_until` needs a timezone (e.g. `2026-11-01T18:00:00+05:30`). Then `POST .../quotes/{quote_id}/send`.
3. Buyer: show the quote's `product_snapshot` (the agreed product details), `total_paise`, and `valid_until`, then `POST /api/v1/orgs/{buyer_org}/orders` with `Idempotency-Key` and `{"quote_id","quote_version","total_paise"}` copied from the quote the user saw. On `409 quote_not_confirmable`, reload the RFQ and show `details.reason` (`product_changed` means the seller edited the product and must send a new version). On `409 insufficient_stock`, tell the user the seller is out of stock.
4. Orders and quotes carry `"simulated": true`. Always show a "simulated, no money moves" label.

Simulated payments (B04A; SPEC.md 9.3). No real money moves; every response has `"simulated": true`:

1. Buyer `admin`/`purchaser`: `POST /api/v1/orgs/{buyer_org}/orders/{order_id}/payment-requests` `{"purpose":"advance","amount_paise":100000,"quote_version":1}`.
2. A different finance user: `GET /api/v1/staff/payment-requests`, then `POST /api/v1/staff/payment-requests/{id}/approve` repeating `order_id`, `purpose`, `amount_paise`, `quote_version` exactly (or `/reject` with a `note`).
3. Finance: `POST /api/v1/staff/payment-requests/{id}/record` (repeat-safe). An approval past its 24 hours is shown as `expired` and no longer blocks a new request.
3a. Corrections (R03, maker-checker): one finance user asks with `POST /api/v1/staff/payment-events/{receipt_id}/reverse` `{"reason"}` (nothing changes yet); a different finance user sees `GET /api/v1/staff/payment-reversals` and approves with `POST /api/v1/staff/payment-reversals/{id}/approve` repeating `order_id`, `receipt_event_id`, `amount_paise`, `reason` (or `/reject` with a `note`). Only the approval inserts the reversal.
4. Either party: `GET /api/v1/orgs/{org_id}/orders/{order_id}/payments` shows `received_paise`, `outstanding_paise`, `refund_due_paise`, requests, and events. Show pending and approved requests as "not received".

Fulfillment (B04B; SPEC.md 9.4): `POST /api/v1/orgs/{org_id}/orders/{order_id}/fulfillment` with `{"action":"dispatch"}` (seller), `"deliver"` (seller or buyer), `"accept"` (buyer; completes the order). `POST .../cancel` `{"reason"}` before dispatch (buyer admin/purchaser or seller admin) restores stock once and cancels open payment requests; recorded simulated receipts then show as `refund_due_paise`. Delivery never marks money received.

Complaints and human help (B04C; SPEC.md 9.5):

- Buyer: `POST /api/v1/orgs/{buyer_org}/orders/{order_id}/cases` `{"category","description","urgency"}`; both parties: `GET /api/v1/orgs/{org_id}/cases[/{id}]`, `POST .../cases/{id}/updates` `{"body"}`, `.../evidence` (metadata: filename, content type, size, sha256); buyer: `.../reopen`, `.../close`.
- Support staff: `GET /api/v1/staff/cases?scope=unassigned|mine`, `POST /api/v1/staff/cases/{id}/take|investigate|resolve|updates` (`"visibility":"internal"` notes are never shown to the parties).
- In a conversation, `POST /api/v1/orgs/{org_id}/conversations/{id}/handoff` (or typing "person"/"మనిషి") pauses the assistant. `GET .../conversations/{id}/messages` returns the newest 100 messages (oldest first, each with an integer `id`); poll with `?after={last id}` to show the person's new `agent` messages and scroll back with `?before={first id}` (`limit` up to 500; a short page means no more). Support: `GET /api/v1/staff/handoffs`, `POST /api/v1/staff/handoffs/{id}/take|messages|release`; after release the summary is no longer available to that person.

Reports (B04D; SPEC.md 9.6): `GET /api/v1/orgs/{org_id}/reports/summary?from=2026-09-01&to=2026-09-30` (default: this month, India time). `sales` and `purchases` are separate; `received_paise` counts only recorded simulated receipts minus reversals; requests waiting for approval are shown apart. Saying "report" to the assistant gives the same numbers.

Assistant (no model or API key needed):

1. `POST /api/v1/orgs/{org_id}/conversations`, then send each user message to `.../conversations/{id}/messages` as `{"text"}` and show `reply`.
2. When `pending_action` is present, show the reply (it reads back product, quantity, and total) and a separate Confirm button. That button calls `POST /api/v1/orgs/{org_id}/pending-actions/{id}/confirm`. Typing "yes" does not confirm anything.
3. After any later message the old Confirm button no longer works (`409 pending_action_not_active`); it also expires after 10 minutes.

Try with `lakshmi.admin@example.test` (English) or `suresh.buyer@example.test` (Telugu): `find 6A one-way switch 100`, `quote`, `2`, `10`, `Guntur`, Confirm; then as `anitha.catalog@example.test` draft and send a quote; then `order`, `1`, Confirm.

Fictional demo users (seed data):

| Email | Organization | Role |
| --- | --- | --- |
| ravi.seller@example.test | Sri Lakshmi Switchgear (manufacturer) | admin |
| anitha.catalog@example.test | Sri Lakshmi Switchgear | catalog_manager |
| lakshmi.admin@example.test | Godavari Electricals (distributor, buys and sells) | admin |
| suresh.buyer@example.test | Godavari Electricals | purchaser |
| meena.viewer@example.test | Godavari Electricals | viewer |
| kiran.retail@example.test | Vizag Home Electric Store (retailer, buys only) | admin |
| farah.finance@example.test | none (platform staff) | finance |
| arjun.finance@example.test | none (platform staff) | finance (second approver for reversals) |
| sanjay.support@example.test, vani.support@example.test | none (platform staff) | support |

Staff roles come only from seed data or direct operator setup; no API grants them. `GET /api/v1/me` returns `staff_roles`.

## Layout

```text
app/main.py       app, CORS, error handlers, /health
app/config.py     settings; fail-closed auth checks
app/auth.py       local demo tokens, current user, organization membership
app/identity.py   local sign-in, /me, organizations
app/catalog.py    seller products, stock adjustments, buyer discovery
app/trade.py      RFQs, quote versions, order confirmation
app/conversation.py  deterministic assistant and pending actions
app/models.py     tables and constraints
app/seed.py       fictional demo data
alembic/          migrations
tests/            PostgreSQL integration tests
```

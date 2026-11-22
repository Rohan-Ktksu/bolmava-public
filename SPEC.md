# Bolmava backend specification

Owner: Rohan-Ktksu. Tasks: B01, B04S, F00 interface boundary. Updated: 31 October 2026 (Asia/Kolkata).

Status: accepted shared API/business contract. B02, B03/R02 and B04/R03/R03a are implemented and merged. Section 9 specifies simulated operations. Contract changes require an update to this file before dependent work continues.

Scope follows [PRODUCTION_ARCHITECTURE.md](PRODUCTION_ARCHITECTURE.md): account membership, seller registration, catalog and stock, buyer discovery, RFQ, quote, confirmed order, and deterministic conversation. Simulated approvals/payments, fulfillment, complaints, human handoff, and reports are specified in section 9. This file specifies the shared API, not UI layout. Speech, WhatsApp, real payments, and provider integrations remain separate tasks.

## 1. Assumptions (pending P01 validation)

| ID | Assumption | Effect if wrong |
| --- | --- | --- |
| A1 | First category is electrical switches (modular wall switches, bell pushes). | Product fields in section 4.4 change; schema migration required. |
| A2 | Telugu (`te`) and English (`en`) are the only UI languages. Business records are stored in canonical structured fields; free text is stored as entered. | Add language codes to the check constraint. |
| A3 | One stock location per seller organization. Stock is counted in the product's selling unit. | Add a locations table and per-location stock. |
| A4 | One product per RFQ and one line per quote in Milestone 1. | Multi-line RFQs need line tables; totals logic is already per-line. |
| A5 | Prices are per selling unit, ex-works, excluding simulated tax. Freight is quoted per quote. | Price-basis field becomes required per product. |
| A6 | Simulated GST is 18% (1800 basis points) on all lines and is labeled simulated. No tax-compliance claim. | Rate becomes per product HSN code. |
| A7 | Discovery is visible to any signed-in user, including exact available quantity. | Replace quantity with a stock band if sellers object. |
| A8 | Delivery area is a list of city names; no geocoding. | Add pincodes/distance later. |
| A9 | PostgreSQL major version 16 locally, in CI, and on RDS (ap-south-1 supports 16). | Upgrade all three together. |

## 2. Identity and authentication boundary

### 2.1 Local fictional-user mode (B02, implemented)

- Enabled by `AUTH_MODE=local`. Only valid when `APP_ENV` is `local` or `test`. The application refuses to start if `APP_ENV=production` and `AUTH_MODE=local`.
- `POST /api/v1/auth/local/session` takes the email of a seeded fictional user and returns a bearer token. There is no password: this mode exists to demonstrate the workflow with fictional data and is not an authentication system.
- Tokens are `<user_id>.<expiry_unix>.<hmac_sha256>` signed with `LOCAL_AUTH_SECRET`, valid for 12 hours. Users with `is_fictional = false` cannot obtain local tokens.
- Every response from local mode carries no special marker; the frontend must display a persistent "Demo: fictional users, simulated money" label.

### 2.2 Production identity (not implemented; required before any real user)

- `AUTH_MODE=cognito`. Cognito user pool in ap-south-1 authenticates the person. The API verifies the access token signature against the pool JWKS, `iss`, `exp`, `token_use = access`, and `client_id`. The verified `sub` maps to `users.cognito_sub` (column added with the Cognito task).
- The current code fails closed: `AUTH_MODE=cognito` raises a startup error until verification is implemented.
- Organization membership and roles always come from PostgreSQL, never from token claims.
- Browser session handling (revised 31 October): the F00 React/Vite local demo holds its fictional bearer token in memory and calls the API through a same-origin Vite `/api` proxy; reload requires sign-in again. A `VITE_` variable or browser storage must not hold credentials. Before real-user production, define and implement a separate same-origin auth gateway/session service that holds verified Cognito tokens in `HttpOnly; Secure; SameSite=Lax` cookies and forwards bearer tokens to the API. Protect cookie-authenticated mutations against CSRF and verify origin. Vite itself is only the frontend build/dev tool, not this session service. Privileged platform staff require MFA. This production design is not implemented or approved for real users.
- No custom production password storage.

### 2.3 Roles (organization-scoped)

An organization has capabilities `can_sell` and `can_buy` (at least one is true). A person has one role per organization through a membership.

| Permission | admin | catalog_manager | purchaser | viewer |
| --- | --- | --- | --- | --- |
| Read own organization data | yes | yes | yes | yes |
| Create/edit products, adjust stock (`can_sell` org) | yes | yes | no | no |
| Create RFQs, confirm orders (`can_buy` org) — B03 | yes | no | yes | no |
| Create/send quotes (`can_sell` org) — B03 | yes | yes | no | no |
| Manage memberships — later | yes | no | no | no |

The organization creator becomes `admin`. Platform support/finance roles are Milestone 2 and are not organization memberships.

## 3. Organization isolation rules

- Every private record carries `org_id`. Every organization-scoped route has the form `/api/v1/orgs/{org_id}/...`. The backend loads the caller's membership for `{org_id}`; if there is none, it returns `404 not_found` (no existence disclosure).
- A record looked up by id inside an organization route is also filtered by `org_id`; a record of another organization returns `404 not_found`.
- Public catalog data (section 6.4) is limited to active products of selling organizations and the seller's display name, city, and simulated verification status. Drafts, inactive products, stock movements, audit events, and memberships are private.
- RFQs, quotes, and orders (B03) are visible only to members of the buyer and seller organizations on that record.

## 4. Data model

PostgreSQL 16. All ids are UUIDs, timestamps are `timestamptz` in UTC (displayed in Asia/Kolkata), money is `bigint` paise. Constraint names follow the SQLAlchemy naming convention in `backend/app/models.py`. All schema changes go through Alembic migrations.

### 4.1 users (B02)

`id`, `email` (unique case-insensitive via `lower(email)` index), `display_name`, `preferred_language` (`te`|`en`), `is_fictional` (bool, default true), `created_at`.

### 4.2 organizations (B02)

`id`, `name`, `city`, `state`, `can_sell`, `can_buy` (check: at least one true), `verification_status` (`simulated_unverified`|`simulated_verified`, default unverified), `is_fictional`, `created_at`.

### 4.3 memberships (B02)

`id`, `org_id` → organizations, `user_id` → users, `role` (check: one of section 2.3), `created_at`. Unique `(org_id, user_id)`.

### 4.4 products (B02)

| Field | Type / constraint | Meaning |
| --- | --- | --- |
| `org_id` | FK organizations | Seller. |
| `sku` | varchar(64), unique per org | Seller's code. |
| `name`, `name_te` | varchar(200); `name_te` nullable | Display names. |
| `category` | check `electrical_switch` | A1. |
| `brand`, `model` | varchar(80) | |
| `rating_amps` | smallint > 0 | e.g. 6, 16. |
| `voltage_v` | smallint > 0 | e.g. 240. |
| `ways` | smallint in (1, 2) | One-way or two-way. |
| `unit` | `piece`\|`box` | Selling unit. |
| `pack_size` | int ≥ 1 | Pieces per unit (1 for `piece`). |
| `moq` | int ≥ 1 | Minimum order, in units. |
| `price_paise` | bigint > 0, ≤ 10^12 | Price per unit, ex-works, excluding simulated tax (A5). |
| `available_qty` | int ≥ 0 | Units in stock. Changed only through stock movements. |
| `lead_time_days` | smallint ≥ 0 | |
| `delivery_cities` | text[] | A8. |
| `status` | `active`\|`inactive` | Only active products are discoverable or quotable. |
| `version` | int ≥ 1 | Incremented by every edit; required for edits (optimistic concurrency). |
| `created_at`, `updated_at` | timestamptz | |

### 4.5 stock_movements (B02)

Append-only. `org_id`, `product_id`, `delta` (int ≠ 0), `reason` (`restock`|`correction`|`damage`|`order`|`order_cancel`), `note`, `resulting_qty` (≥ 0), `actor_user_id` (null for seed data), `idempotency_key`, `order_id` (nullable column added by the B03 migration), `created_at`. Unique `(org_id, idempotency_key)`.

### 4.6 audit_events (B02)

Append-only application history: `id` (bigint identity), `org_id`, `actor_user_id`, `action` (e.g. `org.created`, `product.created`, `product.updated`, `stock.adjusted`), `entity_type`, `entity_id`, `data` (jsonb), `created_at`. Written in the same transaction as the change. Not tamper-proof against database operators.

### 4.7 rfqs (B03)

`id`, `buyer_org_id`, `seller_org_id`, `product_id`, `quantity` (units, ≥ product MOQ at creation), `delivery_city`, `needed_by` (date, nullable), `note`, `status` (`open`|`quoted`|`closed`|`cancelled`), `created_by`, `created_at`, `idempotency_key` (R04, migration 0008; null only for RFQs created before it). Check `buyer_org_id <> seller_org_id`. Unique `(buyer_org_id, idempotency_key)`.

### 4.8 quotes (B03)

One row per version. `id`, `rfq_id`, `version` (unique with `rfq_id`), `status` (`draft`|`sent`|`accepted`|`rejected`|`expired`|`superseded`), `product_id`, `quantity`, `unit_price_paise`, `discount_paise` (≥ 0), `freight_paise` (≥ 0), `tax_bp` (simulated, default 1800), `subtotal_paise`, `tax_paise`, `total_paise`, `advance_paise` (0 ≤ advance ≤ total; recorded, not collected in M1), `valid_until` (timestamptz), `created_by`, `sent_at`, `created_at`.

- `subtotal = quantity × unit_price − discount` (must be > 0)
- `tax = (subtotal + freight) × tax_bp / 10000`, rounded half up to whole paise using integer arithmetic: `(x * bp + 5000) // 10000`
- `total = subtotal + freight + tax`
- Totals are computed by the backend; clients never submit totals except as the confirmation check in section 5.
- Partial unique index: at most one `sent` quote per RFQ. Sending version n marks the previous `sent` version `superseded` in the same transaction. Accepted terms are immutable.
- Only the newest draft of an `open` or `quoted` RFQ can be sent, and only before its `valid_until`; otherwise `409 quote_not_sendable`. Drafts are visible only to the seller. Quote and order quantity always equal the RFQ quantity.
- A buyer rejecting a `sent` quote marks it `rejected` and sets the RFQ back to `open`, so the seller can send a new version.
- Database checks enforce `subtotal = quantity × unit_price − discount > 0`, `total = subtotal + freight + tax`, and `0 ≤ advance ≤ total`.
- `product_snapshot` (jsonb, R02): the product's sku, names, brand, model, rating, voltage, ways, unit, and pack size when the draft was created. It is the agreed specification. If the live product's values differ, sending (`409 quote_not_sendable`) and confirming (`409 quote_not_confirmable`, reason `product_changed`) are refused and the seller must create a new version. Price, stock, MOQ, lead time, delivery cities, and status are not part of it. Migration 0003 filled existing quotes from their product's then-current values.
- A quote is expired when the database's current time (`clock_timestamp()`, read after the row locks are held, not the transaction-start `now()`) is at or after `valid_until`. A background expiry job is not needed in M1: reads report `expired` when the time has passed.

### 4.9 orders (B03)

`id`, `quote_id` (unique — one order per quote), `buyer_org_id`, `seller_org_id`, snapshot of product name/sku/specs, `quantity`, `unit_price_paise`, `discount_paise`, `freight_paise`, `tax_paise`, `total_paise`, `advance_paise`, `status` (`confirmed`|`cancelled`|`completed`), `confirmed_by`, `idempotency_key`, `created_at`. Unique `(buyer_org_id, idempotency_key)`. The order is labeled simulated; no payment is collected.

### 4.10 conversations, messages, pending_actions (B03)

- `conversations`: `id`, `org_id`, `user_id`, `channel` (`web` only in M1), `language`, `state` (jsonb slot values for the active intent), `created_at`. Private to the owning user within the organization.
- `messages`: `id`, `conversation_id`, `role` (`user`|`assistant`), `text`, `created_at`.
- `pending_actions`: `id`, `conversation_id`, `org_id`, `actor_user_id`, `action` (`create_rfq`|`confirm_order`), `payload` (jsonb including exact quote id and version), `expires_at` (10 minutes), `status` (`pending`|`confirmed`|`expired`|`cancelled`), `result_id`.

## 5. Transaction and concurrency rules

1. **Stock adjustment (B02).** One statement: `UPDATE products SET available_qty = available_qty + :delta, version = version + 1 WHERE id = :id AND org_id = :org AND available_qty + :delta >= 0 RETURNING available_qty`. No row → `409 insufficient_stock`. The movement row and audit event commit in the same transaction. Requests sharing an organization and `Idempotency-Key` are serialized with a transaction-scoped PostgreSQL advisory lock taken before the replay lookup. A repeated key, including a concurrent retry, returns the original movement with `200` without applying it again; reusing a key with a different body returns `409 idempotency_key_reused`.
2. **Product edit (B02).** `UPDATE ... WHERE id AND org_id AND version = :expected_version`. Mismatch → `409 version_conflict`.
3. **Order confirmation (B03).** Request carries `Idempotency-Key`, `quote_id`, `quote_version`, `total_paise`. In one transaction:
   1. Take the same transaction-scoped advisory lock on `(buyer_org_id, idempotency_key)` as rule 1. If an order exists for `(buyer_org_id, idempotency_key)`: return it with `200` if it is for the same quote/version, else `409 idempotency_key_reused`.
   2. Lock the RFQ row, then the quote row (`FOR UPDATE`), in that order; require buyer membership with `admin` or `purchaser`. Every trade write (draft, send, reject, confirm) locks the RFQ before the quote and the product stock row last, so these operations cannot deadlock.
   3. Require status `sent` (so it is the RFQ's current version: sending a newer version supersedes it), `quote_version` equal to the quote's version, current database time before `valid_until`, `total_paise` equal to the stored total, and the quote's bound product terms equal to the live product (section 4.8). Else `409 quote_not_confirmable` with `details.reason` one of `already_accepted`, `superseded`, `not_sent`, `expired`, `total_mismatch`, `product_changed`. A draft or another buyer's quote returns `404`. An unsent newer draft does not block confirming the sent version.
   4. Conditional stock decrement (rule 1) with reason `order`. Failure → `409 insufficient_stock`, nothing committed.
   5. Insert order (unique `quote_id` blocks a second order from a different key), mark quote `accepted`, RFQ `closed`, write audit events for both organizations.
   Two concurrent confirmations of the last stock are serialized by the row update; exactly one succeeds. Expiry is checked again with `clock_timestamp()` after the stock update, before commit.
4. **Pending action confirmation (B03).** Executes the same business function as the form endpoint after rechecking actor, organization, expiry, and current quote version. Expiry uses `clock_timestamp()` after locking the pending action and again after the business call; if the deadline passed while waiting for locks, the business change is rolled back and the action is marked `expired`. The assistant's order readback uses the quote's `product_snapshot`, so it matches the resulting order. A pending action from another conversation or user returns `404`.
5. Outbox and SQS are not used in Milestone 1 because no Milestone 1 action has an asynchronous consumer. They arrive with notifications in Milestone 2 (`outbox_events` written in the business transaction).

## 6. API contract

Base path `/api/v1`. JSON only. Authenticated routes require `Authorization: Bearer <token>`. The live OpenAPI document is served at `/openapi.json` and interactive docs at `/docs`; generate frontend TypeScript types from it.

### 6.1 Errors

All errors use one shape:

```json
{"error": {"code": "insufficient_stock", "message": "Not enough stock for this change.", "details": null}}
```

| HTTP | code | When |
| --- | --- | --- |
| 400 | `validation_error` | Body/query fails validation; `details` lists fields. |
| 400 | `idempotency_key_required` | Missing `Idempotency-Key` on a route that needs it. |
| 401 | `unauthenticated` | Missing, malformed, expired, or invalid token. |
| 403 | `forbidden` | Member lacks permission, or organization lacks the capability. |
| 404 | `not_found` | Record does not exist or is outside the caller's organizations. |
| 409 | `conflict` | Unique value already used (e.g. SKU). |
| 409 | `version_conflict` | Edit based on an old product version. |
| 409 | `insufficient_stock` | Stock would go below zero. |
| 409 | `idempotency_key_reused` | Same key, different request. |
| 409 | `quote_not_confirmable` | B03, section 5 rule 3; `details.reason` says why. |
| 409 | `quote_not_sendable` | B03: not the newest draft, RFQ closed, draft already past `valid_until`, or the product's bound terms changed since drafting. |
| 409 | `pending_action_not_active` | B03: the assistant's proposal is `expired`, `cancelled`, or otherwise not pending; `details.status` says which. |

### 6.2 Health and local auth (B02)

| Method and path | Auth | Request | Response |
| --- | --- | --- | --- |
| `GET /health` | none | | `200 {"status":"ok","database":"ok"}` |
| `GET /api/v1/auth/local/users` | none, local mode only | | `200 [{"email","display_name","preferred_language"}]` fictional users |
| `POST /api/v1/auth/local/session` | none, local mode only | `{"email"}` | `200 {"access_token","token_type":"bearer","expires_at"}`; `401` unknown email |

In Cognito mode the local routes are not mounted (`404`).

### 6.3 Identity and organizations (B02)

| Method and path | Permission | Request | Response |
| --- | --- | --- | --- |
| `GET /api/v1/me` | signed in | | `200 {"id","email","display_name","preferred_language","memberships":[{"role","organization":Org}]}` |
| `POST /api/v1/orgs` | signed in | `{"name","city","state","can_sell","can_buy"}`; optional header `Idempotency-Key` (1–80 chars) | `201 Org`; caller becomes `admin`; status `simulated_unverified`. The same person repeating the same key with the same body gets `200` and the same organization; a different body gets `409 idempotency_key_reused` (F05, migration 0011) |
| `GET /api/v1/orgs/{org_id}` | member | | `200 Org` |

`Org = {"id","name","city","state","can_sell","can_buy","verification_status","is_fictional","created_at"}`

Seller registration in M1 is creating an organization with `can_sell = true`. Verification stays `simulated_unverified` unless set by seed data; a simulated verification flow is a later task.

### 6.4 Seller catalog and stock (B02)

| Method and path | Permission | Request | Response |
| --- | --- | --- | --- |
| `GET /api/v1/orgs/{org_id}/products` | member | | `200 [Product]` all statuses |
| `POST /api/v1/orgs/{org_id}/products` | admin/catalog_manager, `can_sell` | `ProductCreate` | `201 Product` with `available_qty = 0`, `version = 1` |
| `GET /api/v1/orgs/{org_id}/products/{id}` | member | | `200 Product` |
| `PATCH /api/v1/orgs/{org_id}/products/{id}` | admin/catalog_manager | `{"version", ...any ProductCreate field}` | `200 Product`; `409 version_conflict` |
| `POST /api/v1/orgs/{org_id}/products/{id}/stock-adjustments` | admin/catalog_manager | header `Idempotency-Key` (1–80 chars); `{"delta","reason","note"}`; reason one of `restock`,`correction`,`damage` | `201 StockMovement`; `200` same movement on replay |
| `GET /api/v1/orgs/{org_id}/products/{id}/stock-movements` (F01b) | member | query `limit` (1–100, default 20), `before` (a movement id from an earlier page) | `200 {"items":[StockHistoryItem],"next_before"}` newest first |

`ProductCreate = {"sku","name","name_te"?,"brand","model","rating_amps","voltage_v","ways","unit","pack_size","moq","price_paise","lead_time_days","delivery_cities":[],"status"}`

`Product = ProductCreate + {"id","org_id","category","available_qty","version","created_at","updated_at"}`

`StockMovement = {"id","product_id","delta","reason","note","resulting_qty","created_at"}`

`StockHistoryItem = {"id","delta","reason","note","resulting_qty","created_at","order_id","actor_name"}`. Ordered by `created_at` then `id`, newest first; `before` returns movements strictly older than that movement (keyset paging, so new movements never shift a page). `next_before` is the last item's id when an older page exists, else `null`. A `before` id that is not a movement of this product returns `400 validation_error`; another organization's product returns `404`. `actor_name` is the acting user's display name only when that user is a member of this organization; it is `null` for seed data and for order movements, whose actor is the buyer (those carry `order_id` instead).

### 6.5 Buyer discovery (B02)

`GET /api/v1/catalog/products` — signed in. Query: `q` (matches name, name_te, brand, model, case-insensitive), `rating_amps`, `ways`, `city` (in `delivery_cities`, case-insensitive), `quantity` (requires `available_qty >= quantity` and `moq <= quantity`), `max_price_paise`, `limit` (1–100, default 20), `offset`. Only `active` products of `can_sell` organizations. Ordered by `price_paise`, then `id`.

Response `200 {"items":[CatalogProduct],"applied_filters":{...},"limit","offset"}`. `applied_filters` echoes the filters every item satisfies, so the interface can explain why each result matched. A result is a possible supplier, not an interested seller or a confirmed sale.

`CatalogProduct = Product fields except version/timestamps + {"seller":{"id","name","city","verification_status"}}`

`GET /api/v1/catalog/products/{id}` returns one `CatalogProduct` or `404` (inactive products are not found).

### 6.6 RFQ, quotes, orders (B03)

| Method and path | Permission |
| --- | --- |
| `POST /api/v1/orgs/{buyer_org}/rfqs` header `Idempotency-Key`, `{"product_id","quantity","delivery_city","needed_by","note"}` → `201 Rfq` (replay `200`) | buyer admin/purchaser, `can_buy` |
| `GET /api/v1/orgs/{org_id}/rfqs` and `/rfqs/{id}` | member of buyer or seller org on the record |
| `POST /api/v1/orgs/{seller_org}/rfqs/{id}/quotes` `{"unit_price_paise","discount_paise","freight_paise","advance_paise","valid_until"}` → draft | seller admin/catalog_manager |
| `POST /api/v1/orgs/{seller_org}/quotes/{id}/send` | seller admin/catalog_manager |
| `GET /api/v1/orgs/{org_id}/quotes/{id}` | buyer or seller member |
| `POST /api/v1/orgs/{buyer_org}/quotes/{id}/reject` | buyer admin/purchaser |
| `POST /api/v1/orgs/{buyer_org}/orders` header `Idempotency-Key`, `{"quote_id","quote_version","total_paise"}` → `201 Order` (replay `200`) | buyer admin/purchaser |
| `GET /api/v1/orgs/{org_id}/orders` and `/orders/{id}` | buyer or seller member |

Response shapes (B03, implemented):

- `Rfq = {"id","buyer_org_id","seller_org_id","product_id","quantity","delivery_city","needed_by","note","status","created_at","buyer_org_name","seller_org_name","product_name","product_name_te","product_unit"}`. The names and unit (F01a) are read-only display values from the current organization and product rows, so both parties can recognize the record; agreed terms live in the quote's `product_snapshot`. `GET /rfqs/{id}` adds `"quotes":[Quote]` in version order (drafts only for the seller).
- `Quote = {"id","rfq_id","version","status","product_id","quantity","unit_price_paise","discount_paise","freight_paise","tax_bp","subtotal_paise","tax_paise","total_paise","advance_paise","valid_until","product_snapshot","sent_at","created_at","simulated":true}`. `status` reads `expired` once a sent quote passes `valid_until`. `valid_until` must include a timezone.
- `Order = {"id","quote_id","quote_version","buyer_org_id","seller_org_id","product_id","product_snapshot","quantity", money fields as Quote, "status","fulfillment_status","confirmed_by","created_at","buyer_org_name","seller_org_name","simulated":true}`. The organization names (F01a) are read-only display values. `product_snapshot` is the quote's bound product terms (identical to the quote's `product_snapshot`).
- The order's stock movement is recorded in the seller organization with reason `order`, `order_id`, and idempotency key `order:{quote_id}`.
- RFQ creation requires an active product of another selling organization and `quantity ≥ moq` (`400` otherwise). Stock is checked at order confirmation, not at RFQ time.
- RFQ idempotency (R04): the form endpoint requires `Idempotency-Key` (1–80 characters; missing → `400 idempotency_key_required`). Keys are scoped to the buyer organization. After the role check, the request takes the same transaction-scoped advisory lock on `(buyer_org_id, key)` as section 5 rule 1, then looks up an RFQ with that key: the same `product_id`, `quantity`, `delivery_city`, `needed_by` and `note` return the original RFQ with `200` and change nothing (even if the product has since become inactive); any difference returns `409 idempotency_key_reused`. The unique constraint backs this up. A client creates one key per form intent and reuses it for retries. The assistant's `create_rfq` pending action uses the key `pending:{pending_action_id}` through the same function.

### 6.7 Deterministic conversation (B03)

- `POST /api/v1/orgs/{org_id}/conversations` → `201 {"id","language","created_at"}` (language from the user's preference)
- `GET /api/v1/orgs/{org_id}/conversations` → the caller's own conversations in this organization, newest first, at most 20, each `{"id","language","created_at","support_case_id","support_status"}` (F01d: lets the owner resume after signing in again; colleagues' conversations are never listed). `support_case_id` and `support_status` (`queued`|`assigned`|`released`) come from the conversation's latest handoff, null if none (F06: a complaint can lead the owner back to its support chat, also after hand-back).
- `GET /api/v1/orgs/{org_id}/conversations/{id}` (owner only; others `404`) → `{"id","language","created_at","handoff":null|Handoff,"pending_action":null|pending_action}` (F01d). `handoff` is the active (`queued`|`assigned`) handoff in the `HandoffOut` shape of section 9.5, so the owner sees the paused state after a reload; it is `null` once released. `pending_action` is the conversation's one `pending` proposal whose `expires_at` is still in the future by the database clock, else `null`. Reading changes nothing.
- `POST /api/v1/orgs/{org_id}/conversations/{id}/messages` `{"text"}` → `200 {"reply","pending_action":null|{...}}`
  - Optional header `Idempotency-Key` (1–80 characters; F01d), scoped to the conversation and checked under the conversation lock. Repeating the key with the same text stores nothing new and returns `200` with the reply that was stored after that message, and the conversation's live `pending` proposal only if that message is still the newest user message (otherwise `null`). The same key with different text → `409 idempotency_key_reused`. A unique `(conversation_id, idempotency_key)` index backs this up. Clients send one key per composed message and reuse it for retries.
- `GET /api/v1/orgs/{org_id}/conversations/{id}/events` (owner only; others `404`; F01d live updates) → `text/event-stream`. Sends `event: ready` once subscribed, `event: changed` after any committed insert or update of this conversation's messages, handoffs or pending actions, and a `: keepalive` comment every 15 seconds. Events carry no text or ids beyond the event name; the client reads what changed through the owner-only message and status routes, so the stream reveals nothing those routes do not. Source: row triggers call `pg_notify('conversation_events', conversation_id)` (migration 0010), delivered at commit; one listener connection per API process fans them out to open streams. The stream ends after 5 minutes so the client reconnects and is re-authorized with its current token. Clients keep a slower safety poll for missed events (for example while the listener reconnects).
- `POST /api/v1/orgs/{org_id}/pending-actions/{id}/confirm` → `200 {"action":"create_rfq","rfq":Rfq}` or `{"action":"confirm_order","order":Order}`. Pressing confirm again returns the same result. Business errors are those of the form endpoints (`403`, `409 quote_not_confirmable`, `409 insufficient_stock`, ...); `409 pending_action_not_active` when expired or cancelled.

`pending_action = {"id","action","payload","expires_at"}`. Only the newest proposal in a conversation is confirmable: every new message cancels earlier pending actions. A pending action belongs to the user and organization that created it; anyone else gets `404`. Conversations are private to their user. The assistant excludes the caller's own organization's listings from search results. Saying `cancel`/`రద్దు` clears the current step.

The assistant uses keyword and number matching in English and Telugu for the intents `find_product`, `request_quote`, `show_quote`, and `confirm_order`. Telugu number words (ఒకటి to పది, పదహారు, ఇరవై, ముప్పై, యాభై, వంద) count as digits, and the spoken forms ఆమ్/ఆంప్స్/ఆంపియర్ and ampere (amp) టు వే (two-way), and కోట్/కోటేషన్ (quote) are accepted, because browser speech writes them (F04). It asks one missing slot at a time, reads back product, quantity, and total in rupees before creating a pending action, and never invents prices or stock: every value comes from the database. No model or API key is needed. An optional model may later propose the same structured intents; backend checks are unchanged.

## 7. Acceptance criteria

### B02 (implemented and tested against PostgreSQL 16)

1. Migrations apply to an empty database with `alembic upgrade head` and downgrade to base.
2. Seed data creates three fictional organizations, their users, and switch products; rerunning the seed changes nothing.
3. A fictional user obtains a local token; an invalid, tampered, or expired token returns `401`; production configuration with local auth refuses to start.
4. A user creates an organization and becomes its admin.
5. A catalog manager creates and edits a product; a stale `version` returns `409`; a purchaser or viewer receives `403`; a buying-only organization cannot create products.
6. A member of another organization receives `404` for the organization, its product list, and its products.
7. Stock adjustments apply once per idempotency key; going below zero returns `409`; concurrent decrements of the same stock never oversell.
8. Discovery returns only active products of selling organizations and respects every filter.
9. Records survive application restart (stored in PostgreSQL).

### B03 (implemented on `backend/b03-trade-workflow`, tested against PostgreSQL 16)

1. Fictional distributor creates an RFQ; manufacturer sends a quote; distributor confirms the exact version once; stock decreases once.
2. Rejected cases: expired quote, superseded version, altered total, insufficient stock, repeated confirmation with a different key for the same quote, viewer or seller attempting to confirm, other organizations reading the RFQ/quote/order.
3. Two concurrent confirmations for the last stock: exactly one order.
4. The deterministic conversation completes find → quote request → confirm using a pending action; an expired pending action returns a safe error.

## 8. Open questions for the owner

1. Should exact available quantity be visible to all signed-in users (A7), or only a stock band?
2. Is 18% simulated GST acceptable for the demo label (A6)?
3. Which cities should seed data use? Current seeds use Vijayawada, Guntur, and Visakhapatnam.
4. Should a buyer be able to send an RFQ to several sellers at once in M1 (A4 allows one)?
5. Default quote validity: proposed 72 hours.
6. Cognito pool, region, and hosted UI choice need AWS account access (P02).
7. Discovery sorts by price per selling unit, so a box of 10 and a single piece are not directly comparable. Should discovery also show price per piece (`price_paise / pack_size`)?
8. (B04S, provisional) Simulated payment approvals expire after 24 hours; recorded receipts can only be reversed in full. Confirm or change.
9. (B04S, provisional) An order is "delayed" when it is not cancelled, not yet delivered, and older than 7 days. Should this use the product lead time instead?
10. (B04S, provisional) Evidence for complaints is metadata only (file name, type, size, checksum, description). File upload/storage waits for the S3 decision.

## 9. Simulated operations (B04S contract for B04A–B04E)

Everything in this section is a fictional demonstration. Money is simulated INR in integer paise with the existing 18% simulated tax; nothing here is a real payment, tax, accounting, escrow, or lending product. Every payment response carries `"simulated": true`. No payment, messaging, ticketing, or storage provider is integrated.

### 9.1 Provisional choices (P01 still open)

| ID | Choice | Why |
| --- | --- | --- |
| O1 | One open payment request (`pending_approval` or `approved`) per order at a time. | Prevents duplicate requests without a separate idempotency table. |
| O2 | Approval valid 24 hours; recording after that returns `409 approval_expired`. | Approvals must not stay usable forever. |
| O3 | A recorded receipt is reversed only in full, once. | Simple, auditable corrections; partial corrections = full reversal + new request. |
| O4 | Cancellation only before dispatch. | Stock has not left the seller; later problems go through complaints. |
| O5 | Evidence is metadata only. | No file storage provisioned (S3 gated by P02). |
| O6 | Delayed = not cancelled, not delivered/accepted, created more than 7 days ago. | No lead time in the order snapshot. |
| O7 | Report periods are whole Asia/Kolkata calendar days, `from` and `to` inclusive. | Matches how users talk about "today" and "this month". |

### 9.2 Platform staff and permissions (staff grants implemented in B04A)

Platform staff roles are separate from organization roles and stored in `staff_grants` (`id`, `user_id`, `role` = `finance`|`support`, `note`, `created_at`, `revoked_at`). Partial unique index: one active grant per user and role. Grants are created only by `python -m app.seed` (fictional staff) or direct database setup by the operator. There is no API to grant, request, or self-assign a staff role, and being an organization `admin` grants nothing at platform level. `GET /api/v1/me` adds `"staff_roles": ["finance"|"support", ...]` (active grants only).

Fictional staff (seed): `farah.finance@example.test` and `arjun.finance@example.test` (finance; two people so a reversal can be requested and approved by different users), `sanjay.support@example.test` and `vani.support@example.test` (support). They belong to no organization.

| Action | Who may do it |
| --- | --- |
| Request a simulated payment on an order | Buyer org `admin`/`purchaser` |
| See an order's payment requests, events, balance | Members of the order's buyer or seller org; any `finance` staff |
| Approve / reject a payment request | `finance` staff who did not create the request (maker-checker) |
| Record an approved request as a simulated receipt | `finance` staff |
| Request a reversal of a recorded receipt (no ledger change) | `finance` staff, with a reason |
| Approve / reject a reversal request (approval inserts the reversal) | `finance` staff who did not create that reversal request (maker-checker; R03) |
| Dispatch, mark delivered | Seller org `admin`/`catalog_manager` |
| Mark delivered | also buyer org `admin`/`purchaser` |
| Accept delivery | Buyer org `admin`/`purchaser` |
| Cancel an order (before dispatch) | Buyer org `admin`/`purchaser` or seller org `admin` |
| Open a complaint, reopen, close a resolved complaint | Buyer org `admin`/`purchaser` |
| Add a party-visible complaint update | Buyer/seller org members except `viewer`; the assigned support person |
| See a complaint and its party-visible updates and evidence metadata | Members of its buyer or seller org; the assigned support person |
| See internal notes; add internal notes; investigate; resolve | Only the assigned support person |
| See the unassigned queue (id, category/urgency, created time only) and take an item | Any `support` staff |
| Request a human in a conversation | The conversation's owner |
| See a handoff summary; send agent messages; release automation | Only the assigned support person, while the handoff is `assigned` (a released handoff gives its former assignee `404` for the summary; R03) |
| Organization reports | Members of that organization (all roles) |

Staff routes live under `/api/v1/staff/...` and return `403 forbidden` without the needed grant. A staff user who is not assigned to a case or handoff gets `404` for it (no existence disclosure). Finance staff cannot see complaints or conversations; support staff cannot see payment records.

### 9.3 Simulated payments (B04A; implemented, self-tested, review pending)

Records:

- `payment_requests`: `id`, `order_id`, `purpose` (`advance`|`balance`), `amount_paise` (> 0), `currency` (`INR` only), `quote_version` (the order's agreed terms version), `status` (`pending_approval` → `approved`|`rejected`; `approved` → `recorded`|`expired`; any open → `cancelled` when the order is cancelled), `requested_by`, `decided_by`, `decided_at`, `decision_note`, `approval_expires_at`, `created_at`. Check `decided_by <> requested_by`. Partial unique index on `order_id` where status in (`pending_approval`, `approved`) (O1).
- `payment_events` (append-only): `id`, `order_id`, `kind` (`receipt`|`reversal`), `amount_paise` (> 0), `request_id` (receipts; unique), `reverses_event_id` (reversals; unique), `reason`, `recorded_by`, `created_at`. A reversal's amount equals its receipt's amount (O3).
- `payment_reversals` (R03): `id`, `receipt_event_id`, `order_id`, `amount_paise` (the receipt's), `currency` (`INR`), `reason`, `status` (`pending_approval` → `executed`|`rejected`|`expired`), `requested_by`, `decided_by`, `decided_at`, `decision_note`, `expires_at` (request time + 24 h), `reversal_event_id` (unique; set on execution), `created_at`. Check `decided_by <> requested_by`. Partial unique index on `receipt_event_id` where status is `pending_approval`.

Balance (computed from saved events, never stored): `received = Σ receipts − Σ reversals`; `due = 0` if the order is cancelled else `total_paise`; `outstanding = max(due − received, 0)`; `refund_due = max(received − due, 0)`. Approval alone is not a receipt. Pending and approved requests are reported separately and never counted as received.

Rules:

1. Request (`POST /api/v1/orgs/{buyer_org}/orders/{order_id}/payment-requests` `{"purpose","amount_paise","quote_version"}`): order `confirmed`, `quote_version` equals the order's, `amount ≤ outstanding`; for `advance`, `amount ≤ advance_paise − already received`. A second open request returns `409 open_request_exists` with `details.request_id`; repeating the same purpose/amount by the same requester returns the open request with `200`. Under the order lock and before those checks, an `approved` request whose `approval_expires_at` has passed (database clock) is saved as `expired`, so it no longer holds the open slot and the buyer can submit a fresh request without anyone attempting a receipt (R03).
2. Approve (`POST /api/v1/staff/payment-requests/{id}/approve` `{"order_id","purpose","amount_paise","quote_version","note"}`): the body must repeat the request's bound terms exactly, otherwise `409 terms_mismatch`; the approver must differ from the requester (`403 self_approval`); status must be `pending_approval`. Sets `approval_expires_at = clock_timestamp() + 24h`. Reject (`.../reject` `{"note"}`) needs the same distinct actor.
3. Record (`POST /api/v1/staff/payment-requests/{id}/record`): lock order, then request (lock order: order → payment request → product stock). Requires `approved`, current database time before `approval_expires_at` (else the request becomes `expired`, `409 approval_expired`), order not cancelled, and `amount ≤ outstanding` recomputed under the lock (`409 exceeds_outstanding`). Inserts one receipt; replays return the same receipt with `200` (unique `request_id`).
4. Reverse, maker-checker (R03; lock order: order → reversal request):
   - Request: `POST /api/v1/staff/payment-events/{id}/reverse` `{"reason"}` → `201` PaymentReversal (`pending_approval`). Changes no ledger row. Only receipts (`409 invalid_transition`); an already reversed receipt → `409 invalid_transition` with `details.status = "reversed"`. One pending reversal per receipt: the same requester and reason gets it back with `200`, anything else `409 open_request_exists` with `details.request_id`. A pending reversal past `expires_at` is first saved as `expired`.
   - Approve: `POST /api/v1/staff/payment-reversals/{id}/approve` `{"order_id","receipt_event_id","amount_paise","reason","note"}`. The approver must differ from the reversal's requester (`403 self_approval`) — also when that person holds several roles or approved/recorded the receipt; the body must repeat the bound order, receipt, amount and reason exactly (`409 terms_mismatch`); status must be `pending_approval` (`409 invalid_transition`); database time after the locks must be before `expires_at` (else saved `expired`, `409 approval_expired`). In the same transaction it inserts the one reversal event (`recorded_by` = approver, `reason` from the request) and sets `executed`, `reversal_event_id`. Repeating an executed approval returns it with `200`. The unique `reverses_event_id` keeps one reversal per receipt under concurrency.
   - Reject: `POST /api/v1/staff/payment-reversals/{id}/reject` `{"note"}`, same distinct actor, only from `pending_approval`.
   - Queue: `GET /api/v1/staff/payment-reversals?status=pending_approval|executed|rejected|expired` (finance only).
   PaymentReversal = `{"id","receipt_event_id","order_id","amount_paise","currency","reason","status","requested_by","decided_by","decided_at","decision_note","expires_at","reversal_event_id","created_at","simulated":true}`.
5. Read: `GET /api/v1/orgs/{org_id}/orders/{order_id}/payments` and `GET /api/v1/staff/orders/{order_id}/payments` → `{"order_id","total_paise","advance_paise","received_paise","outstanding_paise","refund_due_paise","requests":[...],"events":[...],"simulated":true}`. `GET /api/v1/staff/payment-requests?status=pending_approval` lists the finance queue. Approved requests past their expiry are listed under `status=expired`, not `approved`, whether or not the expiry has been saved yet (database clock).
6. Every change writes audit events for both organizations in the same transaction. The assistant may not approve, record, or reverse anything.

### 9.4 Fulfillment and cancellation (B04B; implemented, self-tested, review pending)

Orders gain `fulfillment_status` (`pending` → `dispatched` → `delivered` → `accepted`), plus append-only `fulfillment_events` (`id`, `order_id`, `status`, `actor_user_id`, `note`, `created_at`). Order status becomes `completed` on acceptance and `cancelled` on cancellation; payment status is separate (section 9.3) and no fulfillment step creates a receipt.

`POST /api/v1/orgs/{org_id}/orders/{order_id}/fulfillment` `{"action":"dispatch"|"deliver"|"accept","note"}` and `POST /api/v1/orgs/{org_id}/orders/{order_id}/cancel` `{"reason"}`. `GET /api/v1/orgs/{org_id}/orders/{order_id}/fulfillment-events` lists events (both parties). `Order` responses now include `fulfillment_status`. Each action locks the order row first, then rechecks state; a wrong party gets `403`, a wrong state `409 invalid_transition` with `details.status`. Repeating the action just applied returns `200` with the order unchanged.

Cancel (O4): only while `confirmed` and `pending`. In one transaction: order `cancelled`, stock restored with a `+quantity` movement of reason `order_cancel`, `order_id`, key `order-cancel:{order_id}` (unique, so stock is restored exactly once), open payment requests set to `cancelled`, audit events. Recorded receipts stay; the balance then shows `refund_due`, which finance handles by reversal (no automatic refund).

### 9.5 Complaints and human handoff (B04C; implemented, self-tested, review pending)

- `cases`: `id`, `order_id`, `buyer_org_id`, `seller_org_id`, `category` (`damaged`|`wrong_product`|`missing_quantity`|`delay`|`quality`|`payment`|`other`), `description`, `urgency` (`low`|`normal`|`high`), `status`, `assigned_to`, `resolution`, `reopen_count`, `opened_by`, `created_at`, `updated_at`.
- States: `open` → `assigned` (support takes it) → `investigating` → `resolved` (resolution text required) → `closed`. A buyer may reopen `resolved` → `assigned` (or `open` if unassigned). Closed is final.
- `case_updates`: `visibility` `parties`|`internal`; internal updates are returned only to the assigned support person.
- `case_evidence` metadata (O5): `filename`, `content_type`, `size_bytes`, `sha256`, `description`, `added_by`. No download URL exists.
- `handoffs`: `id`, `conversation_id`, `org_id`, `case_id` (optional, must belong to the same organization), `urgency`, `status` `queued` → `assigned` → `released`, `requested_by`, `assigned_to`, timestamps. One active (`queued`|`assigned`) handoff per conversation.
- A conversation with an active handoff is paused: the assistant stores the user's message, proposes nothing, and replies (and stores the reply, F01d, so a reloaded transcript shows it) that a person is handling it; requesting a handoff cancels pending actions; confirming any pending action of a paused conversation returns `409 conversation_paused`. Only the assigned support person can release it (`POST /api/v1/staff/handoffs/{id}/release`), after which the assistant resumes with its saved state. A handoff linked to a complaint (`case_id`) still waits in the shared queue, so any support person can take it. In `GET /staff/handoffs?scope=unassigned`, `your_case_id` is set only for the support person who holds the linked complaint (null for everyone else), so that person can take the chat from the complaint page (F06).
- Handoff summary (assigned person only, and only while the handoff is `assigned`; R03): `GET /staff/handoffs/{id}` and a repeated `take` on a released handoff return `404` and `409 invalid_transition` respectively, so release ends the person's access to later messages and the current case. A former assignee keeps only the `HandoffOut` rows in `?scope=mine` (no transcript). R03a: GET and take check the assignment and build the whole summary (messages, case, order status) in one transaction holding the conversation → handoff row locks, the same locks release takes; take commits its assignment only after the summary is built. A release therefore waits for an in-flight summary, and a summary never contains anything committed after its handoff was released. Requester name and language, organization name, the last 10 messages of this conversation only, linked case/order ids and statuses, and pending actions that were cancelled by the handoff. Nothing from the organization's other conversations.
- Endpoints: `POST /api/v1/orgs/{org}/orders/{order_id}/cases`, `GET /api/v1/orgs/{org}/cases`, `GET .../cases/{id}`, `POST .../cases/{id}/updates|evidence|reopen|close`, `POST /api/v1/orgs/{org}/conversations/{id}/handoff`, `GET /api/v1/staff/cases?scope=unassigned|mine`, `POST /api/v1/staff/cases/{id}/take|investigate|resolve|updates`, `GET /api/v1/staff/handoffs?scope=unassigned|mine`, `POST /api/v1/staff/handoffs/{id}/take|messages|release`, `GET /api/v1/staff/handoffs/{id}`.
- No complaint transition creates, approves, records, or reverses money.
- Message history (R03): `GET /api/v1/orgs/{org}/conversations/{id}/messages?limit=&before=&after=` (owner only; others `404`) returns `user`, `assistant`, and `agent` messages, oldest first, each `{"id","role","text","created_at"}`. `id` is a stable, increasing integer. `limit` 1–500, default 100. With no cursor: the newest `limit` messages. `before={id}`: the `limit` messages just older than that id (scroll back). `after={id}`: the next `limit` messages newer than that id (polling; repeat with the last id received until a short page). `before` and `after` together → `400 validation_error`. A page shorter than `limit` means there is nothing further in that direction, so every message is reachable without gaps or duplicates.
- Implementation notes: Typing `human`, `person`, `agent`, `support`, `మనిషి`, or `సహాయకుడు` in the conversation requests a handoff, the same as the endpoint. `POST /staff/cases/{id}/take` returns the full case (with internal notes) and `POST /staff/handoffs/{id}/take` returns the summary; repeating either by the same person is harmless, while another person gets `409 invalid_transition`. Lock order: conversation, then pending action or handoff. A pending action created before a handoff stays cancelled after release. Ordinary form endpoints keep working during a handoff; only the assistant is paused.

### 9.6 Reports (B04D; implemented, self-tested, review pending)

`GET /api/v1/orgs/{org_id}/reports/summary?from=YYYY-MM-DD&to=YYYY-MM-DD` (O7; default: the current Asia/Kolkata month; at most 366 days) returns separate `sales` (org as seller) and `purchases` (org as buyer) blocks:

- `orders` and `order_value_paise`: non-cancelled orders created in the period; `cancelled_orders`.
- `received_paise`: net simulated receipts (receipts − reversals) whose events fall in the period.
- `outstanding_paise` and `refund_due_paise`: as of now across all the org's orders (section 9.3 formula).
- `awaiting_approval_paise` and `approved_unrecorded_paise`: open requests, never counted as received.

Plus `open_cases` (not resolved/closed, either side), `delayed_orders` (O6) with a bounded list (`limit` 1–100, default 20), period boundaries in UTC and their Asia/Kolkata dates, and `"simulated": true`. Implementation notes: `period_start_utc` is Asia/Kolkata midnight of `from` and `period_end_utc` is midnight after `to` (exclusive), so 23:30 IST on the last day belongs to that day. `order_value_paise` and `cancelled_orders` count orders by creation time; `received_paise` counts receipt/reversal events by their own time; balances and open requests are as of now. Approved requests past their approval expiry are not counted. Response: `{"org_id","from_date","to_date","period_start_utc","period_end_utc","sales":Totals,"purchases":Totals,"open_cases","delayed_orders_count","delayed_orders":[{"order_id","side","fulfillment_status","created_at"}],"simulated":true}`. Errors: `400 validation_error` for `to` before `from` or more than 366 days. The deterministic assistant's `report` intent (`report`, `sales`, `summary`, `how much`, `రిపోర్ట్`, `అమ్మకాలు`, `లెక్క`) calls the same function for the current month and states that money is simulated; it distinguishes possible suppliers (search), enquiries (RFQs), quotes, orders, recorded receipts, and completed orders.

### 9.7 New error codes

| HTTP | code | When |
| --- | --- | --- |
| 403 | `self_approval` | Approver or decider is the requester. |
| 409 | `open_request_exists` | O1. |
| 409 | `terms_mismatch` | Approval body differs from the request's bound order/purpose/amount/version. |
| 409 | `approval_expired` | O2; also a reversal request approved after its `expires_at`. |
| 409 | `exceeds_outstanding` | Request or receipt above the remaining amount (or above the agreed advance). |
| 409 | `invalid_transition` | Fulfillment, payment-request, case, or handoff action not allowed from the current state; `details.status`. |
| 409 | `conversation_paused` | A person owns the conversation. |

### 9.8 Deferred

Partial reversals and refunds as their own flow; payment provider references; tax invoices; order amendments; partial delivery and returns; evidence files, malware scanning and retention; SLA timers; notifications that reach a closed browser or other channels (Web Push through a browser push service, email, SMS, WhatsApp), which need the outbox/SQS worker, production sessions and a subscription store (F01d adds live in-app updates and browser notifications while the app is open, section 6.7); support-agent availability; report exports; multi-currency.

### 9.9 Acceptance (per slice; PostgreSQL tests)

- **B04A**: one advance requested, approved by a different finance user, recorded once, balance exact; self-approval, tampered approval, expired approval, non-finance, outsider, over-recording (including two concurrent recordings), and duplicate recording fail or replay with no partial rows; a reversal references its receipt and restores the balance. R03: a reversal request changes no ledger row; only a different finance user's exact-terms approval inserts it; self-approval (including a dual-role requester), tampered, rejected, expired, and concurrent requests/approvals leave at most one reversal; an expired approval frees the open slot for a replacement without a recording attempt, and concurrent replacements leave one open request.
- **B04B**: dispatch → deliver → accept by the right parties; wrong party, wrong state, repeated, and concurrent cancel/dispatch are safe; cancellation restores stock exactly once and leaves recorded receipts as `refund_due`.
- **B04C**: buyer opens a case; support takes it; internal notes hidden from parties and other staff; a pending action from before handoff is refused; agent message and release work; outsiders and unassigned staff get 404. R03: a released assignee gets no summary (GET 404, repeat take 409) and never sees later messages; the current assignee and the owner keep their views; a revoked grant gets 403; message history pages backwards and polls forwards over every message without gaps or duplicates.
- **B04D**: fixed fixtures reconcile across empty periods, cancellations, reversals, and an org that both buys and sells; the assistant's report text uses the same numbers.
- **B04E**: scripted API journey, fresh migration, upgrade from 0003, seed rerun, restart, and backup/restore into a separate database give the same totals.

All five slices are implemented and tested.

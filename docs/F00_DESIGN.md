# F00 frontend design foundation

Owner: Rohan-Ktksu. Written 31 October 2026 for frontend slice F00. Telugu copy is a first draft and needs human review (F03).

## Direction

A shop counter, not a control room. Warm paper surfaces, deep indigo ink for structure, one turmeric‑terracotta accent kept for the main action on each screen. Every control has a text label. Each page opens by saying what it is for, then shows the next useful action. No charts, gradients or icon‑only buttons.

## Route map

| Path | Who sees it | F00 state | Purpose |
| --- | --- | --- | --- |
| `/signin` | Anyone | Built | Pick a fictional demo person; token stays in memory |
| `/` | Signed in | Built | "What can I do now?" task cards for the current organization and role |
| `/products` | Signed in | Built | Find products: words, city, quantity, amps, ways (real `/catalog/products`) |
| `/products/:id` | Signed in | Built | Product detail: unit, pack, MOQ, stock, delivery cities, seller (real `/catalog/products/{id}`) |
| `/help` | Signed in | Built | Plain‑word guide to request → quote → confirmed order → simulated payment → delivered; how to reach a person |
| `/more` | Signed in, phone | Built | Remaining destinations, organization, language, sign out |
| `/requests`, `/requests/:id`, `/products/:id/request` | Buyer org (`can_buy`); actions for admin/purchaser | Built, F01a | Requests & quotes: request, quote review, explicit confirm, reject |
| `/orders`, `/orders/:id` | Any organization member; actions by party and role | Built, F01a + F01c | My orders (bought and sold), agreed terms, delivery timeline with dispatch/deliver/accept/cancel |
| `/enquiries`, `/enquiries/:id` | Seller org (`can_sell`); actions for admin/catalog_manager | Built, F01a | Enquiries & quotes: draft, check backend totals, send |
| `/my-products`, `/my-products/new`, `/my-products/:id` | Seller org (`can_sell`); changes for admin/catalog_manager | Built, F01b | Products & stock: list, create/edit, hide/show, reviewed stock changes |
| `/reports` | Any organization member | Placeholder, F01 | Plain‑language report |
| `/support` | `support` staff | Placeholder, F02 | Queue and assigned conversations |
| `/finance` | `finance` staff | Placeholder, F02 | Approval queue and simulated payment records |

Placeholders say plainly that the screen is not built yet. Navigation visibility follows `/me` roles for orientation only; the API stays the permission authority.

## Layouts

Phone (360 px):

```text
┌──────────────────────────────┐
│ Fictional data · Simulated ₹ │  persistent demo strip
├──────────────────────────────┤
│ Bolmava      [EN|తె] [Help] │
│ ▾ Godavari Electricals (buyer)│  organization switcher
├──────────────────────────────┤
│ Find products                │  page title + one-line purpose
│ [ search words........ ][Go] │
│ ▸ More filters: city, qty…   │  disclosure keeps results on screen 1
│ ┌──────────────────────────┐ │
│ │ 6A one-way switch, box   │ │  product card: name (EN + తె),
│ │ ₹450 / box · MOQ 5       │ │  price/unit, MOQ, stock, seller
│ │ Sri Lakshmi · Vijayawada │ │
│ └──────────────────────────┘ │
├──────────────────────────────┤
│ Home  Products  Orders  Help  More │ labeled bottom bar (≤4 + More)
└──────────────────────────────┘
```

Desktop (≥ 960 px):

```text
┌───────────────────────────────────────────────────────────────┐
│ Fictional data · Simulated money — no real payments            │
├──────────────┬────────────────────────────────────────────────┤
│ Bolmava      │ Organization ▾          Language [EN|తె]  Sign out │
│              ├────────────────────────────────────────────────┤
│ Home         │ Find products                                   │
│ Find products│ Words · City · Quantity · Amps · Ways   [Search] │
│ Requests…    │ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│ My orders    │ │ card     │ │ card     │ │ card     │          │
│ Help         │ └──────────┘ └──────────┘ └──────────┘          │
│ Talk to a    │                                                 │
│ person       │                                                 │
└──────────────┴────────────────────────────────────────────────┘
```

## Tokens

Defined once in `frontend/src/index.css` `:root`.

| Token | Value | Use |
| --- | --- | --- |
| `--paper` | `#FAF6EF` | Page background |
| `--paper-2` | `#F1EADD` | Sunken areas, nav rail |
| `--card` | `#FFFDF9` | Cards, inputs |
| `--line` | `#E2D7C5` | Borders |
| `--ink` | `#1F1D3D` | Text and structure (indigo ink); 15:1 on paper |
| `--ink-2` | `#55516F` | Secondary text; 7:1 on paper |
| `--indigo` | `#2E3275` | Selected navigation, links, demo strip |
| `--accent` | `#B4471F` | Primary action only; white text 5.4:1 |
| `--accent-soft` | `#F6E2D6` | Accent tint behind task cards |
| `--danger` | `#A3262A` | Errors |
| `--focus` | `#2E3275` ring, `#F5C46A` on dark | 3 px outline, 2 px offset |
| Type | Anek Telugu (headings), Noto Sans Telugu (body); both cover Latin and Telugu | 14 / 16 / 18 / 22 / 28 / 34 px; body line height 1.6 for Telugu matras |
| Space | 4 / 8 / 12 / 16 / 24 / 32 / 48 px | `--s1`…`--s7` |
| Radius | 10 px controls, 16 px cards | |
| Touch | 44 px minimum target | |

Motion is limited to a short focus/hover transition and is removed under `prefers-reduced-motion`.

## Reusable components

- `Shell`: demo strip, header (brand, organization switcher, language control, help, sign out), desktop rail / phone bottom bar from one destination list.
- `PageHead`: title plus one sentence saying what the page is for.
- `TaskCard`: large labeled link with a short explanation (home page).
- `ProductCard` and `Fact` rows: name in English and Telugu, price per unit, pack, MOQ, stock, seller, city.
- `Money`: integer paise shown as INR with a "fictional" or "simulated" qualifier; display only, never calculates.
- `Loading`, `Empty`, `ErrorState` (message from the API error envelope, a retry button, never invented values), announced through `role="status"` / `role="alert"`.
- `NotBuilt`: honest placeholder for later slices.

## Data and session choices

- Vite proxies `/api` to `http://localhost:8000`; the browser only calls same origin.
- The demo bearer token lives in a module variable. A reload signs the person out by design. No local storage, cookies or `VITE_` variables hold it. Language choice alone is kept in local storage.
- Fetching uses one small hook that aborts the previous request when inputs change, so a slow old search cannot overwrite a newer one. F01 mutations may justify a cache library; F00 does not.

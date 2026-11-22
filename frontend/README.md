# Bolmava frontend (F00)

React 19 + Vite 8 + TypeScript 7 + React Router 7. Design note: [../docs/F00_DESIGN.md](../docs/F00_DESIGN.md). Fictional data and simulated money only.

Built in F00: fictional demo sign-in, `/me` organization switcher, role-aware navigation, English/Telugu control, catalog browse and product detail. Built in F01a: request a quote, seller quote draft/send, buyer review with explicit order confirmation or rejection, and order views. Other destinations are labeled "Not built yet".

## Run locally (Windows PowerShell)

Needs Node.js 24 (tested with 24.20.0 / npm 11.19.0) and the backend API running on port 8000 (see [../backend/README.md](../backend/README.md)).

```powershell
cd frontend
npm ci
npm run dev        # http://localhost:5173 ; /api is proxied to http://localhost:8000
```

Other commands:

```powershell
npm run build      # type check (tsc -b) and production build into dist/
npm test           # node:test checks of role-aware navigation, action permissions and rupee parsing
npm run lint       # oxlint
npm run e2e        # Playwright browser tests against real FastAPI + PostgreSQL; needs E2E_DATABASE_URL (see ../docs/CI.md)
```

## Rules this app keeps

- The browser calls only same-origin `/api`; `vite.config.ts` forwards it to FastAPI. Backend CORS is unchanged.
- The demo bearer token is held in a module variable (`src/api.ts`). Reloading the page signs you out on purpose. No token in local storage, cookies or `VITE_` variables. Only the language choice is saved in local storage.
- Permissions, prices and stock come from the API. Navigation follows `/me` roles for orientation only.
- Money arrives as integer paise and is only formatted for display.

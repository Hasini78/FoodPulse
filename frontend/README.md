# FoodPulse frontend

React 19 + TypeScript + Vite + Tailwind 4 + Plotly. No new dependencies were added in the UI refresh.

## Run

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to http://localhost:8000
npm run build
```

## Routes

| Path | Page |
| --- | --- |
| `/` | Landing page (dark hero) |
| `/login` | Sign in |
| `/app` | Dashboard overview |
| `/app/restaurants`, `/sentiment`, `/segments`, `/churn`, `/recommendations`, `/forecast`, `/customers`, `/insights` | Analytics pages |

## Hero photo

The landing and sign-in pages draw a plated-dish backdrop in SVG. To use a real photograph, save it as `public/hero.jpg`; it is layered over the artwork automatically.

## Sign-in

The dashboard is open by default. To require sign-in, set `VITE_REQUIRE_AUTH=true`.
`src/lib/auth.ts` posts `username` and `password` (form-encoded) to `POST /auth/login` and expects `{ "access_token": "..." }`. Edit that one function if your backend differs. The token is sent as a Bearer header on every API call.

## Design tokens

Colors, fonts and radii are defined in `src/index.css` under `@theme`. Chart colors live in `src/lib/chartTheme.ts`.

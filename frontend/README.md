# RosterLab frontend

Next.js 16 (App Router) + TypeScript + Tailwind v4 + TanStack Query + dnd-kit +
Recharts. See the [root README](../README.md) for the full project.

```bash
npm install
npm run dev        # http://localhost:3000 (expects backend on :8000)
npm run test       # vitest unit tests
npm run test:e2e   # Playwright (requires an ingested local database)
npm run lint && npx tsc --noEmit
npm run build
```

`/api/v1/*` is rewritten to `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`)
in `next.config.ts` — the browser never talks to data providers directly.

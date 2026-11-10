# GigBid web app (React + Vite + TypeScript)

Screens (src/app): sign-in, onboarding, inbox, job detail, proposal studio, pipeline,
messages, agent run viewer, analytics, settings. Design: docs/DESIGN.md.

```bash
npm install
npm run gen:api      # regenerate src/lib/api/schema.d.ts from the FastAPI schema (never hand-edit it)
npm run dev          # http://localhost:5173 (proxies /api to the API on :8000)
npm run build        # dist/, served by FastAPI at /
npx playwright test  # 5 end-to-end tests against a throwaway server (scripts/e2e_server.py)
```

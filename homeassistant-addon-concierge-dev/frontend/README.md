# Concierge frontend

Lit + TypeScript SPA, built with Vite, served by the backend (FastAPI) as
static files. Speaks the AG-UI protocol over SSE — see
`docs/superpowers/notes/2026-07-10-backend-handoff.md` for the wire contract.

## Dev workflow

    # terminal 1 — backend on :8098
    cd ../backend
    CONCIERGE_DATA_DIR=/tmp/concierge-dev CONCIERGE_HA_URL=... \
    CONCIERGE_HA_TOKEN=... CONCIERGE_API_KEY=... uv run python -m concierge

    # terminal 2 — Vite dev server with /agui + /threads proxied
    npm install
    npm run dev

## Checks

    npm run test        # vitest (happy-dom)
    npm run lint        # eslint
    npm run typecheck   # tsc --noEmit
    npm run build       # tsc + vite build -> dist/

All API paths are RELATIVE (`./agui`) — Supervisor ingress serves the app
under a dynamic path prefix, so absolute paths would break. Keep it that way.

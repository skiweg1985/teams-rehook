# Agent Notes

This repository is `teams-messenger`, an authenticated internal tool for relaying webhook messages into Microsoft Teams.

## Stack

- Backend: FastAPI in `backend/app`
- Database: SQLAlchemy with SQLite locally and Postgres in Docker
- Frontend: React, Vite and TypeScript in `frontend`
- Proxy: HAProxy routes `/api/*` to the backend and all other paths to the frontend

## Commands

- Frontend build: `cd frontend && npm run build`
- Backend syntax check: `python3 -m py_compile backend/app/*.py backend/app/routers/*.py backend/app/core/*.py`
- Full validation: `npm run test`
- Docker stack: `cp .env.example .env && docker compose up -d --build`

## Implementation Notes

- Keep authenticated writes behind `require_csrf` on the backend and `X-CSRF-Token` in the frontend API client.
- The app's primary domain objects are webhook routes, Teams bot conversation references and webhook delivery events.
- Preserve the neutral CSS-token design language unless a concrete product has a stronger brand direction.
- Avoid reintroducing third-party integration domain concepts unless the new app explicitly needs them.

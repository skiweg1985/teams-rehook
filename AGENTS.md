# Agent Notes

This repository is `codex-app-skeleton`, a template for authenticated internal tools.

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
- Replace `DemoItem` with the app's first real domain object when creating a concrete project from this template.
- Preserve the neutral CSS-token design language unless a concrete product has a stronger brand direction.
- Avoid reintroducing third-party integration domain concepts unless the new app explicitly needs them.

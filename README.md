# codex-app-skeleton

Template for authenticated internal tools, extracted from the redesigned source branch and reduced to a reusable app foundation:

- FastAPI backend with SQLAlchemy, cookie sessions, CSRF protection and bootstrap admin user
- Postgres in Docker, SQLite for quick local backend runs
- React 18, Vite and TypeScript frontend
- CSS-variable design system with light, dark and system theme modes
- Reusable shell, cards, tables, modals, form states, status badges and toast notifications

## Quickstart

```bash
cp .env.example .env
docker compose up -d --build
```

Open:

- Frontend: http://localhost
- API docs: http://localhost/api/v1/docs

Seeded admin login:

```text
admin@example.com
change-me-admin-password
```

## Local Development

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

When running frontend and backend separately, keep `CORS_ORIGINS` aligned with the Vite dev server origin.

## Skeleton Surface

The template intentionally keeps only generic product primitives:

- `/api/v1/auth/login`
- `/api/v1/auth/logout`
- `/api/v1/sessions/me`
- `/api/v1/demo-items`
- `/api/v1/admin/users`
- `/api/v1/admin/logs`
- `/api/v1/health`
- `/api/v1/readyz`

Replace `DemoItem` with the first real domain object of a new app. The frontend Items page is wired to the same CRUD endpoints so the full auth, CSRF, table, modal and toast path is already exercised.

## Validation

```bash
npm run test
```

This runs the frontend production build and Python syntax checks for the backend app.

## Template Notes

- Rename `codex-app-skeleton` in package metadata, container names and UI copy when creating a concrete app.
- Keep session-changing requests behind `X-CSRF-Token`; the frontend stores the token only in React state.
- The design system is plain CSS in `frontend/src/index.css`, centered around neutral surfaces, tight tables and restrained operational UI.

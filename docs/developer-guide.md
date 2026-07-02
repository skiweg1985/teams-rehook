# Developer Guide

## Prerequisites

- Python 3.11 or compatible runtime.
- Node.js and npm.
- Docker and Docker Compose for the full local stack.

## Project Structure

| Path | Purpose |
|---|---|
| `backend/app` | FastAPI application, routers, models, services, settings, security, and startup schema handling. |
| `backend/tests` | Pytest tests for APIs, services, schema backfills, readiness, delivery, and payload handling. |
| `frontend` | React, Vite, TypeScript frontend. |
| `haproxy` | Local HAProxy proxy and development certificate bootstrap. |
| `docs` | Repository documentation and technical notes. |
| `docker-compose.yml` | Local stack with Postgres, backend, frontend, and HAProxy. |

## Local Setup With Docker

```bash
./manage.sh start
```

On first run, `./manage.sh start` launches the guided `.env` setup if needed. Running `./manage.sh setup` explicitly still writes the local `.env` first and then offers to start the stack. The guided wizard offers `local`, `production`, and `custom` profiles; the recommended `local` profile publishes HTTPS on `https://localhost:8443`.

Open (recommended `local` profile):

```text
https://localhost:8443
```

For local credential-free delivery checks while developing integration code, set this explicitly in `.env` and restart the backend:

```text
BOT_DELIVERY_MODE=mock
```

## Local Setup Without Docker

Backend:

```bash
cd backend
pip install --require-hashes -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on port `5173` and proxies `/api` to `PROXY_HTTP_PORT`, defaulting to `8080`.

## Build And Test

From the repository root:

```bash
npm run frontend:build
npm run backend:check
npm run backend:test
npm run test
```

`npm run test` runs the frontend build, backend syntax check, and pytest suite.

## Backend Dependency Updates

Direct backend dependencies are maintained in `backend/requirements.in`.
`backend/requirements.txt` is generated from that file and must be committed with pinned versions and hashes.

```bash
cd backend
python -m pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.txt requirements.in
```

## Backend Notes

Main entry point:

- `backend/app/main.py`

Important modules:

- `backend/app/core/config.py` for environment settings.
- `backend/app/core/settings_overrides.py` for admin-overridable runtime settings.
- `backend/app/models.py` for SQLAlchemy models.
- `backend/app/schemas.py` for Pydantic request/response models.
- `backend/app/routers` for API routes.
- `backend/app/services` for Microsoft Graph, Bot Framework, log retention, and payload normalization logic.
- `backend/app/seed.py` for startup table creation and schema backfill logic.

Authenticated writes should remain behind `require_csrf`. Frontend API calls for those writes should include `X-CSRF-Token`.

## Frontend Notes

Main files:

- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `frontend/src/index.css`

The frontend API client centralizes JSON requests and CSRF header handling. Keep API response types aligned with `backend/app/schemas.py`.

## API Development

When adding or changing endpoints:

1. Add or update Pydantic schemas.
2. Keep authenticated writes protected by `require_csrf`.
3. Update frontend types and API client methods.
4. Add pytest coverage.
5. Update [API reference](api.md) and related user/admin docs.

## Data Model Changes

The repository does not use a dedicated migration framework. Existing startup code creates tables and performs additive/backfill schema updates.

When changing persistent schema:

1. Update `backend/app/models.py`.
2. Update startup/backfill handling in `backend/app/seed.py` if existing databases need compatibility.
3. Add or update tests in `backend/tests`.
4. Update [Data model](data-model.md).

TODO: Decide whether to introduce a formal migration tool before production rollout.

## Coding Conventions

- Follow existing FastAPI, SQLAlchemy, and React patterns in the repository.
- Prefer service modules for Microsoft integration logic.
- Do not expose secrets in API responses, readiness payloads, monitoring payloads, logs, or documentation.
- Keep the frontend visual language aligned with the existing neutral CSS-token design.

## Branching And Pull Requests

No formal branching convention is visible in the repository.

Recommended default:

- Use short topic branches.
- Keep changes scoped.
- Run `npm run test` before requesting review.
- Include documentation updates when behavior, configuration, routes, or operational procedures change.

## Release Process

TODO: Define release versioning, tagging, changelog ownership, supported versions, and rollback policy.

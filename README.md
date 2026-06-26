# Teams Messenger

Authenticated Teams webhook relay for forwarding operational messages into Microsoft Teams conversations.

- FastAPI backend with SQLAlchemy, cookie sessions, CSRF protection and bootstrap admin user
- Webhook route management with stable relay URLs, URL regeneration and delivery tests
- Teams bot conversation reference capture for selecting known Teams targets
- Delivery logs with normalized payloads, request metadata and bot delivery responses
- React 18, Vite and TypeScript frontend with light, dark and system theme modes
- HAProxy routing for `/api/*`, `/auth/*` and frontend traffic

## Quickstart

```bash
cp .env.example .env
docker compose up -d --build
```

Open:

- Frontend: http://localhost:8080
- API docs: http://localhost:8080/api/v1/docs

Proxy ports are configured via `PROXY_HTTP_PORT` and `PROXY_HTTPS_PORT` in `.env` (defaults: `8080` / `8443`).

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

## Application Surface

Teams Messenger exposes authenticated administration endpoints and public relay URLs:

- `/api/v1/auth/login`
- `/api/v1/auth/logout`
- `/api/v1/sessions/me`
- `/api/v1/webhook-routes`
- `/api/v1/webhook-routes/{route_id}/deliveries`
- `/api/v1/webhook-routes/{route_id}/test`
- `/api/v1/webhook-routes/{route_id}/regenerate-url`
- `/api/v1/bot/conversation-references`
- `/api/v1/teams-targets/search`
- `/api/v1/teams-targets/teams/{team_id}/channels`
- `/api/v1/admin/users`
- `/api/v1/admin/logs`
- `/api/v1/health`
- `/api/v1/readyz`

Webhook routes map source systems to Teams bot conversations. Delivery events record incoming webhook attempts, normalized message data and bot adapter responses for troubleshooting.

## Validation

```bash
npm run test
```

This runs the frontend production build, Python syntax checks and backend tests.

## Notes

- Keep session-changing requests behind `X-CSRF-Token`; the frontend stores the token only in React state.
- Use `BOT_DELIVERY_MODE=mock` for local validation without sending Teams messages, and `real` when Bot Framework credentials are configured.
- Leave Microsoft Graph credentials empty to reuse the Bot app registration credentials for target search.

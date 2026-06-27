# Configuration

Teams Rehook uses two configuration layers:

1. Environment settings loaded from `.env` or process environment through `backend/app/core/config.py`.
2. Database overrides for selected runtime settings through the admin settings API/UI and the `app_settings` table.

Database overrides are loaded at startup and after setting changes. Resetting an override restores the environment value.

## Environment Variables

Use `.env.example` as the safe template. Do not commit a populated `.env`.

| Variable / Option | Description | Required | Default | Example | Security relevant |
|---|---|---:|---|---|---:|
| `APP_NAME` | Application name used in FastAPI metadata and health responses. Code default only; not listed in `.env.example`. | No | `Teams Rehook` | `Teams Rehook` | No |
| `APP_VERSION` | Application version used in FastAPI metadata and health responses. Code default only; not listed in `.env.example`. | No | `0.1.0` | `0.1.0` | No |
| `API_V1_PREFIX` | API path prefix used for routers, OpenAPI docs, and generated callback paths. Code default only; not listed in `.env.example`. | No | `/api/v1` | `/api/v1` | No |
| `PROXY_HTTP_PORT` | Host port mapped to HAProxy HTTP listener. Used by Docker Compose and Vite proxy config. | No | `8080` in `.env.example` | `8080` | No |
| `PROXY_HTTPS_PORT` | Host port mapped to HAProxy HTTPS listener. | No | `8443` in `.env.example` | `8443` | No |
| `APP_PUBLIC_BASE_URL` | Public base URL used to build relay and OAuth callback URLs. | No | Code default `http://localhost:8000`; `.env.example` uses `http://localhost:8080` | `http://localhost:8080` | No |
| `FRONTEND_BASE_URL` | Base URL used for generated UI links and OAuth redirects back to the frontend. | No | Code default `http://localhost:5173`; `.env.example` uses `http://localhost:8080` | `http://localhost:8080` | No |
| `CORS_ORIGINS` | Comma-separated origins allowed for credentialed browser requests. Must not be empty. | Yes | Code default `http://localhost:5173,http://localhost` | `http://localhost:8080` | No |
| `DATABASE_URL` | SQLAlchemy database URL. Docker Compose overrides this to Postgres for the backend container. | No | `sqlite:///./app.db` | `postgresql+psycopg2://app:app@postgres:5432/app` | Yes |
| `WEBHOOK_MAX_PAYLOAD_BYTES` | Maximum accepted webhook request body size. | No | `64000` | `64000` | No |
| `LOG_RETENTION_DAYS` | Retention window for delivery, audit, and bot activity logs. `0` means cleanup can remove events older than now. | No | `7` | `7` | No |
| `LOG_CLEANUP_INTERVAL_MINUTES` | Minimum interval between automatic cleanup runs. | No | `60` | `60` | No |
| `MS_APP_TENANT_ID` | Entra tenant ID for Bot Framework and Microsoft Graph token requests. | Required for real Microsoft integrations | Empty | `00000000-0000-0000-0000-000000000000` | No |
| `MS_APP_CLIENT_ID` | Entra app client ID for Bot Framework and Microsoft Graph token requests. | Required for real Microsoft integrations | Empty | `00000000-0000-0000-0000-000000000000` | No |
| `MS_APP_CLIENT_SECRET` | Entra app client secret. | Required for real Microsoft integrations | Empty | `change-me` | Yes |
| `BOTFRAMEWORK_SCOPE` | OAuth scope requested for Bot Framework tokens. | No | `https://api.botframework.com/.default` | `https://api.botframework.com/.default` | No |
| `GRAPH_SCOPE` | OAuth scope requested for Microsoft Graph app-only tokens. | No | `https://graph.microsoft.com/.default` | `https://graph.microsoft.com/.default` | No |
| `BOT_FRAMEWORK_ENABLED` | Enables Bot Framework route setup, delivery, and readiness impact. | No | `true` | `true` | No |
| `GRAPH_LOOKUP_ENABLED` | Enables Graph target search, name refresh, and readiness impact. | No | `true` | `true` | No |
| `GRAPH_DELIVERY_ENABLED` | Enables delegated Graph delivery. Requires Graph lookup to remain enabled. | No | `true` | `true` | No |
| `BOT_DELIVERY_MODE` | `real` sends through Microsoft services; `mock` simulates delivery. Invalid values normalize to `mock`. | No | `real` | `mock` | No |
| `BOT_DEFAULT_SERVICE_URL` | Optional fallback Bot Framework service URL. Route-specific values still take precedence. | Required for some real Bot Framework setups | Empty | `https://smba.trafficmanager.net/emea/` | No |
| `MONITORING_API_KEY` | Bearer token for `/api/v1/monitoring/status`. Empty disables the endpoint with `503`. | Required for monitoring endpoint | Empty | `change-me` | Yes |
| `SESSION_SECRET` | Secret used for session signing and fallback encryption-key derivation. | Yes | `change-me-session-secret` | `change-me` | Yes |
| `SETTINGS_ENC_KEY` | Optional Fernet key for encrypted settings overrides at rest. Falls back to `SESSION_SECRET` if empty. | No | Empty | `change-me` | Yes |
| `SESSION_COOKIE_NAME` | Session cookie name. | No | `teams_rehook_session` | `teams_rehook_session` | No |
| `SESSION_TTL_HOURS` | Session lifetime in hours. | No | `8` | `8` | No |
| `SESSION_SECURE_COOKIE` | Sets the session cookie `Secure` flag. Use `true` behind HTTPS. | No | `false` | `true` | Yes |
| `DEFAULT_ORG_SLUG` | Bootstrap organization slug. Code default only; not listed in `.env.example`. | No | `default` | `default` | No |
| `DEFAULT_ORG_NAME` | Bootstrap organization display name. Code default only; not listed in `.env.example`. | No | `Default Organization` | `Operations` | No |
| `BOOTSTRAP_ADMIN_EMAIL` | Bootstrap admin email. | Yes for first startup | `admin@example.com` | `admin@example.com` | No |
| `BOOTSTRAP_ADMIN_PASSWORD` | Bootstrap admin password. | Yes for first startup | `change-me-admin-password` | `change-me` | Yes |
| `BOOTSTRAP_ADMIN_DISPLAY_NAME` | Bootstrap admin display name. | No | `App Admin` | `App Admin` | No |

## Docker Compose Overrides

`docker-compose.yml` loads `.env` into the backend and overrides only:

```text
DATABASE_URL=postgresql+psycopg2://app:app@postgres:5432/app
```

The bundled Postgres service uses local development credentials:

- `POSTGRES_DB=app`
- `POSTGRES_USER=app`
- `POSTGRES_PASSWORD=app`

Do not reuse these credentials for production.

## Admin-Overridable Runtime Settings

These settings are defined in `backend/app/core/settings_overrides.py` and can be changed through the admin settings API/UI:

| Key | Type | Secret | Validation / Notes |
|---|---|---:|---|
| `bot_delivery_mode` | enum | No | `mock` or `real`. |
| `bot_framework_enabled` | bool | No | Enables Bot Framework setup, delivery, and readiness impact. |
| `graph_lookup_enabled` | bool | No | Enables Graph target search and name refresh. |
| `graph_delivery_enabled` | bool | No | Requires `graph_lookup_enabled=true`. |
| `bot_default_service_url` | url | No | Empty or valid `http`/`https` URL. |
| `webhook_max_payload_bytes` | int | No | Minimum `1024`. |
| `log_retention_days` | int | No | Minimum `0`. |
| `log_cleanup_interval_minutes` | int | No | Minimum `1`. |
| `app_public_base_url` | url | No | Valid `http`/`https` URL. |
| `frontend_base_url` | url | No | Valid `http`/`https` URL. |
| `ms_app_tenant_id` | string | No | Shared Microsoft tenant ID. |
| `ms_app_client_id` | string | No | Shared Microsoft client ID. |
| `ms_app_client_secret` | secret | Yes | Write-only in API responses. |
| `botframework_scope` | string | No | Bot Framework OAuth scope. |
| `graph_scope` | string | No | Microsoft Graph OAuth scope. |

Secret overrides are encrypted at rest using Fernet. The encryption key is `SETTINGS_ENC_KEY` when set, otherwise derived from `SESSION_SECRET`.

## Security Notes

- Replace every `change-me` style placeholder before production-like use.
- Do not publish `.env`.
- Treat relay URLs as secrets.
- Avoid documenting tenant-specific production URLs or credentials in repository docs.

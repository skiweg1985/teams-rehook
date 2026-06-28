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
| `TRUST_X_FORWARDED_FOR` | Allows the backend to use `X-Forwarded-For` as the webhook client IP, but only when the direct client is trusted. Docker Compose overrides this to `true` for the bundled HAProxy. | No | `false` in `.env.example`; Docker backend uses `true` | `true` | Yes |
| `TRUSTED_PROXY_IPS` | Comma-separated trusted proxy IP addresses or CIDR ranges. Docker Compose sets this to the fixed HAProxy IP `172.30.0.10`. | Required if `TRUST_X_FORWARDED_FOR=true` | Empty in `.env.example`; Docker backend uses `172.30.0.10` | `172.30.0.10` | Yes |
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
| `SESSION_SECRET` | Secret used for session signing and OAuth state protection. If omitted, an instance secret is generated and stored at first startup. | No | Generated instance secret | Secret manager value | Yes |
| `SETTINGS_ENC_KEY` | Stable secret string used for encrypted settings overrides and delegated refresh material. If omitted, first startup creates a separate generated key in the database for local/simple shared-database deployments. | No | Generated settings encryption key | Secret manager value | Yes |
| `SESSION_COOKIE_NAME` | Session cookie name. | No | `teams_rehook_session` | `teams_rehook_session` | No |
| `SESSION_TTL_HOURS` | Session lifetime in hours. | No | `8` | `8` | No |
| `SESSION_SECURE_COOKIE` | Sets the session cookie `Secure` flag. Use `true` behind HTTPS. | No | `false` | `true` | Yes |
| `DEFAULT_ORG_SLUG` | Bootstrap organization slug. Code default only; not listed in `.env.example`. | No | `default` | `default` | No |
| `DEFAULT_ORG_NAME` | Bootstrap organization display name. Code default only; not listed in `.env.example`. | No | `Default Organization` | `Operations` | No |

When the default organization has no admin users, the frontend shows the first-run setup flow. That flow creates the first admin from the email, display name, and password entered by the installer. No fixed admin credentials are created by startup.

## Docker Compose Overrides

`docker-compose.yml` loads `.env` into the backend and overrides:

```text
DATABASE_URL=postgresql+psycopg2://app:app@postgres:5432/app
TRUST_X_FORWARDED_FOR=true
TRUSTED_PROXY_IPS=172.30.0.10
```

The fixed trusted proxy IP belongs to the bundled HAProxy service on the internal Compose network. This makes webhook abuse blocking use the real caller from `X-Forwarded-For` instead of grouping all callers under the proxy IP.

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
| `webhook_abuse_blocking_enabled` | bool | No | Enables temporary blocking for repeated failed webhook attempts. |
| `webhook_abuse_failure_limit` | int | No | Minimum `1`; default code value is `10`. |
| `webhook_abuse_window_minutes` | int | No | Minimum `1`; default code value is `10`. |
| `webhook_abuse_initial_block_minutes` | int | No | Minimum `1`; default code value is `10`. |
| `webhook_abuse_max_block_minutes` | int | No | Minimum `1`; default code value is `1440`. |
| `webhook_abuse_cleanup_days` | int | No | Minimum `1`; controls cleanup of inactive abuse tracking records. |
| `log_retention_days` | int | No | Minimum `0`. |
| `log_cleanup_interval_minutes` | int | No | Minimum `1`. |
| `trust_x_forwarded_for` | bool | No | Runtime override for trusting `X-Forwarded-For` from trusted proxies. |
| `trusted_proxy_ips` | string | No | Comma-separated IP addresses or CIDR ranges for trusted reverse proxies. |
| `app_public_base_url` | url | No | Valid `http`/`https` URL. |
| `frontend_base_url` | url | No | Valid `http`/`https` URL. |
| `ms_app_tenant_id` | string | No | Shared Microsoft tenant ID. |
| `ms_app_client_id` | string | No | Shared Microsoft client ID. |
| `ms_app_client_secret` | secret | Yes | Write-only in API responses. |
| `botframework_scope` | string | No | Bot Framework OAuth scope. |
| `graph_scope` | string | No | Microsoft Graph OAuth scope. |

Secret overrides are encrypted at rest using Fernet with `SETTINGS_ENC_KEY`. `SESSION_SECRET` is not used for settings encryption.

## Session Secret And Scaling

`SESSION_SECRET` is intentionally not listed in `.env.example`. For local and simple Docker deployments, leave it unset: the backend creates one instance secret on first startup, stores it in the shared database, and reuses it after restarts. Backend replicas that use the same database will therefore share the same generated secret.

For production-like deployments with strict secret rotation, stateless release requirements, or controlled multi-region rollout, provide `SESSION_SECRET` from the deployment platform's secret manager instead. All backend replicas in the same environment must use the same value. Never use `change-me` style placeholders; startup rejects placeholder session secrets.

## Settings Encryption Key

`SETTINGS_ENC_KEY` protects encrypted application settings, Microsoft client secret overrides, and delegated Graph refresh material. For production-like deployments, provide it through a durable secret manager or `.env` and keep the same value for every backend replica.

If `SETTINGS_ENC_KEY` is omitted, first startup creates a separate generated settings encryption key in the application database. This supports local and simple shared-database Docker deployments, but the key is still tied to that database. Keep the database volume when rebuilding containers.

Changing `SETTINGS_ENC_KEY` without re-encrypting or re-entering existing secrets makes those encrypted values unreadable. Restore the previous key or re-enter/reconnect the affected secret material.

## Security Notes

- Replace every `change-me` style placeholder before production-like use.
- Leave `SESSION_SECRET` unset for the generated shared database-backed instance secret, or provide the same strong deployment-managed value to every backend replica.
- Provide a stable `SETTINGS_ENC_KEY` for production-like deployments, or preserve the generated database-backed settings key in local/simple deployments.
- Do not publish `.env`.
- Treat relay URLs as secrets.
- Avoid documenting tenant-specific production URLs or credentials in repository docs.

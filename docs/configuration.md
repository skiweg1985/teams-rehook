# Configuration

Teams Rehook uses two configuration layers:

1. Environment settings loaded from `.env` or process environment through `backend/app/core/config.py`.
2. Database-backed admin settings through the admin settings API/UI and the `app_settings` table.

Environment-backed settings reset to the environment value. Application-managed settings, including delivery feature switches, reset to their code default.

## Environment Variables

Use `.env.example` as the safe template. For local Docker setup, prefer `./manage.sh setup`; it writes the small infrastructure-focused `.env` that the stack needs. Do not commit a populated `.env`.

| Variable / Option | Description | Required | Default | Example | Security relevant |
|---|---|---:|---|---|---:|
| `APP_NAME` | Application name used in FastAPI metadata and health responses. Code default only; not listed in `.env.example`. | No | `Teams Rehook` | `Teams Rehook` | No |
| `APP_VERSION` | Application version used in FastAPI metadata and health responses. Code default only; not listed in `.env.example`. | No | `0.1.0` | `0.1.0` | No |
| `API_V1_PREFIX` | API path prefix used for routers, OpenAPI docs, and generated callback paths. Code default only; not listed in `.env.example`. | No | `/api/v1` | `/api/v1` | No |
| `PROXY_HTTP_PORT` | Host port mapped to HAProxy HTTP listener. Used by Docker Compose and Vite proxy config. | No | `8080` in `.env.example` | `8080` | No |
| `PROXY_HTTPS_PORT` | Host port mapped to HAProxy HTTPS listener. | No | `8443` in `.env.example` | `8443` | No |
| `COMPOSE_APP_SUBNET` | CIDR used for the internal Docker Compose application network. The backend always trusts this subnet as the direct bundled HAProxy hop. | No | `172.30.0.0/24` in `.env.example` | `172.30.0.0/24` | Yes |
| `APP_PUBLIC_BASE_URL` | Public base URL used to build relay and OAuth callback URLs. | No | Code default `http://localhost:8000`; `.env.example` uses `http://localhost:8080` | `http://localhost:8080` | No |
| `FRONTEND_BASE_URL` | Base URL used for generated UI links and OAuth redirects back to the frontend. | No | Code default `http://localhost:5173`; `.env.example` uses `http://localhost:8080` | `http://localhost:8080` | No |
| `CORS_ORIGINS` | Comma-separated origins allowed for credentialed browser requests. Must not be empty. | Yes | Code default `http://localhost:5173,http://localhost` | `http://localhost:8080` | No |
| `DATABASE_URL` | SQLAlchemy database URL. Bare-process backend defaults to SQLite. Docker Compose uses the bundled Postgres service unless this is set to an external database URL. | No | `sqlite:///./app.db`; Docker Compose builds an internal Postgres URL | `postgresql+psycopg2://app:app@postgres:5432/app` | Yes |
| `POSTGRES_DB` | Database name created when the bundled Postgres volume is initialized. Used by Docker Compose to build the default backend `DATABASE_URL`. | No | `app` in `.env.example` | `teams_rehook` | No |
| `POSTGRES_USER` | Database user created when the bundled Postgres volume is initialized. Used by Docker Compose to build the default backend `DATABASE_URL`. | No | `app` in `.env.example` | `teams_rehook` | Yes |
| `POSTGRES_PASSWORD` | Database password created when the bundled Postgres volume is initialized. Used by Docker Compose to build the default backend `DATABASE_URL`. | No | `app` in `.env.example` | Secret manager value | Yes |
| `WEBHOOK_MAX_PAYLOAD_BYTES` | Maximum accepted webhook request body size. | No | `64000` | `64000` | No |
| `WEBHOOK_ABUSE_BLOCKING_ENABLED` | Enables temporary blocking after repeated failed webhook attempts. Admins can also change this in the Settings UI. | No | `true` | `true` | No |
| `WEBHOOK_ABUSE_FAILURE_LIMIT` | Failed attempts allowed inside the abuse window before a client is blocked. Admins can also change this in the Settings UI. | No | `10` | `5` | No |
| `WEBHOOK_ABUSE_WINDOW_MINUTES` | Rolling failure-count window for abuse tracking. Admins can also change this in the Settings UI. | No | `10` | `15` | No |
| `WEBHOOK_ABUSE_INITIAL_BLOCK_MINUTES` | Duration of the first temporary abuse block. This is environment-only and not exposed as a runtime override. | No | `10` | `30` | No |
| `WEBHOOK_ABUSE_MAX_BLOCK_MINUTES` | Maximum duration for escalated abuse blocks. This is environment-only and not exposed as a runtime override. | No | `1440` | `720` | No |
| `WEBHOOK_ABUSE_CLEANUP_DAYS` | Retention window for inactive abuse tracking buckets. This is environment-only and not exposed as a runtime override. | No | `30` | `14` | No |
| `LOG_RETENTION_DAYS` | Retention window for delivery, audit, and bot activity logs. `0` means cleanup can remove events older than now. | No | `7` | `7` | No |
| `LOG_CLEANUP_INTERVAL_MINUTES` | Minimum interval between automatic cleanup runs. | No | `60` | `60` | No |
| `EVENT_DEBUG_PREVIEWS_ENABLED` | Keeps redacted, size-clipped previews of raw payloads in event log entries. Code default only; not listed in `.env.example`. Admins can also change this in the Settings UI. | No | `false` | `false` | No |
| `TRUST_X_FORWARDED_FOR` | Allows the backend to use `X-Forwarded-For` as the webhook client IP, but only when the direct client is trusted. Docker Compose overrides this to `true` for the bundled HAProxy. | No | `false` in `.env.example`; Docker backend uses `true` | `true` | Yes |
| `TRUSTED_PROXY_IPS` | Comma-separated additional trusted upstream proxy IP addresses or CIDR ranges. The bundled HAProxy subnet is trusted separately through `COMPOSE_APP_SUBNET`. | No | Empty in `.env.example` | `10.0.0.0/24,192.168.10.15` | Yes |
| `MS_APP_TENANT_ID` | Entra tenant ID for Bot Framework and Microsoft Graph token requests. The repository keeps this commented in `.env.example` because operators can also set it in the Settings UI. | Required for real Microsoft integrations | Empty | `00000000-0000-0000-0000-000000000000` | No |
| `MS_APP_CLIENT_ID` | Entra app client ID for Bot Framework and Microsoft Graph token requests. The repository keeps this commented in `.env.example` because operators can also set it in the Settings UI. | Required for real Microsoft integrations | Empty | `00000000-0000-0000-0000-000000000000` | No |
| `MS_APP_CLIENT_SECRET` | Entra app client secret. The repository keeps this commented in `.env.example` because operators can also set it in the Settings UI. | Required for real Microsoft integrations | Empty | `change-me` | Yes |
| `BOTFRAMEWORK_SCOPE` | OAuth scope requested for Bot Framework tokens. The repository keeps this commented in `.env.example` because operators can also set it in the Settings UI. | No | `https://api.botframework.com/.default` | `https://api.botframework.com/.default` | No |
| `GRAPH_SCOPE` | OAuth scope requested for Microsoft Graph app-only tokens. The repository keeps this commented in `.env.example` because operators can also set it in the Settings UI. | No | `https://graph.microsoft.com/.default` | `https://graph.microsoft.com/.default` | No |
| `BOT_DELIVERY_MODE` | `real` sends through Microsoft services; `mock` simulates delivery. Invalid values normalize to `mock`. This remains an environment-only developer override and is not editable in the Settings UI. | No | `real` | `mock` | No |
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

`docker-compose.yml` loads `.env` into the backend and applies these stack defaults:

```text
DATABASE_URL=${DATABASE_URL:-postgresql+psycopg2://${POSTGRES_USER:-app}:${POSTGRES_PASSWORD:-app}@postgres:5432/${POSTGRES_DB:-app}}
COMPOSE_APP_SUBNET=${COMPOSE_APP_SUBNET:-172.30.0.0/24}
TRUST_X_FORWARDED_FOR=${TRUST_X_FORWARDED_FOR:-true}
```

The bundled HAProxy is always trusted through `COMPOSE_APP_SUBNET`. Additional upstream reverse proxies belong in `TRUSTED_PROXY_IPS`. This makes webhook abuse blocking use the caller from `X-Forwarded-For` when the direct proxy hop is the bundled HAProxy, while still allowing an explicit trust chain through approved upstream proxies.

The bundled Postgres service uses local development bootstrap values:

- `POSTGRES_DB=app`
- `POSTGRES_USER=app`
- `POSTGRES_PASSWORD=app`

Do not reuse these values for production. `POSTGRES_*` values are applied by the Postgres image only when a new `postgres_data` volume is initialized. They are not ongoing credential management for an existing database. To rotate credentials for an existing database, change the user/password in Postgres, update `DATABASE_URL` if needed, and restart the backend.

If production database credentials contain URL-special characters, set `DATABASE_URL` explicitly with proper URL encoding instead of relying on the Compose fallback assembled from `POSTGRES_*`.

## Admin Runtime Settings

These settings are defined in `backend/app/core/settings_overrides.py` and can be changed through the admin settings API/UI.
Delivery feature switches are application-managed settings: they default to `true`, are stored in `app_settings` after the UI changes them, and are not read from `.env`.

| Key | Type | Secret | Validation / Notes |
|---|---|---:|---|
| `bot_framework_enabled` | bool | No | Application-managed default `true`; enables Bot Framework setup, delivery, and readiness impact. |
| `graph_lookup_enabled` | bool | No | Application-managed default `true`; enables Graph target search and name refresh. |
| `graph_delivery_enabled` | bool | No | Application-managed default `true`; requires `graph_lookup_enabled=true`. |
| `webhook_max_payload_bytes` | int | No | Minimum `1024`. |
| `webhook_abuse_blocking_enabled` | bool | No | Enables temporary blocking for repeated failed webhook attempts. |
| `webhook_abuse_failure_limit` | int | No | Minimum `1`; default code value is `10`. |
| `webhook_abuse_window_minutes` | int | No | Minimum `1`; default code value is `10`. |
| `log_retention_days` | int | No | Minimum `0`. |
| `log_cleanup_interval_minutes` | int | No | Minimum `1`. |
| `event_debug_previews_enabled` | bool | No | When enabled, event log entries keep redacted, size-clipped previews of raw payloads. Disabled by default; previews are empty when off. |
| `session_secure_cookie` | bool | No | Applies the session cookie `Secure` flag immediately for new logins. |
| `trust_x_forwarded_for` | bool | No | Runtime override for trusting `X-Forwarded-For` from trusted proxies. |
| `cors_origins` | string | No | Comma-separated HTTP/HTTPS origins; scheme, host, and optional port only. |
| `app_public_base_url` | url | No | Valid `http`/`https` URL. |
| `frontend_base_url` | url | No | Valid `http`/`https` URL. |
| `ms_app_tenant_id` | string | No | Shared Microsoft tenant ID. |
| `ms_app_client_id` | string | No | Shared Microsoft client ID. |
| `ms_app_client_secret` | secret | Yes | Write-only in API responses. |

Secret overrides are encrypted at rest using Fernet with `SETTINGS_ENC_KEY`. `SESSION_SECRET` is not used for settings encryption.

Advanced webhook abuse timings stay in environment configuration. Only `webhook_abuse_blocking_enabled`, `webhook_abuse_failure_limit`, and `webhook_abuse_window_minutes` are admin-overridable runtime settings.

`BOTFRAMEWORK_SCOPE` and `GRAPH_SCOPE` are environment settings only. The current admin settings API does not expose runtime overrides for those OAuth scopes.

`TRUSTED_PROXY_IPS` is environment-only because the bundled HAProxy consumes the same value at container start. The admin readiness view reports the effective compose subnet, trusted upstream proxies, and combined trust chain as read-only diagnostics.

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

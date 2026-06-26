# Technical documentation

## Configuration layers

Runtime settings are resolved in two layers:

1. **Environment defaults** — loaded from `.env` / process environment via `Settings` in `backend/app/core/config.py`.
2. **Database overrides** — optional per-key values in the `app_settings` table, managed through the admin API and UI.

`get_effective_settings()` merges environment defaults with active overrides. Resetting an override deletes the database row and restores the environment value.

Infrastructure-bound settings (`DATABASE_URL`, `CORS_ORIGINS`, session cookie configuration, bootstrap credentials) remain environment-only and require a process restart when changed.

## Overridable settings

These settings are defined in `backend/app/core/settings_overrides.py` and can be changed through the Settings UI or admin settings API:

| Key | Type | Secret | Notes |
|-----|------|--------|-------|
| `bot_delivery_mode` | enum | no | `mock` or `real`; invalid values normalize to `mock` at runtime |
| `bot_default_service_url` | url | no | Optional fallback Bot Framework service URL; must be `http` or `https` when set |
| `webhook_max_payload_bytes` | int | no | Minimum `1024` |
| `log_retention_days` | int | no | Minimum `0` |
| `log_cleanup_interval_minutes` | int | no | Minimum `1` |
| `app_public_base_url` | url | no | Used to build relay URLs |
| `frontend_base_url` | url | no | Used for generated UI links, including bot command copy links |
| `ms_app_tenant_id` | string | no | Shared Entra tenant ID for Bot Framework and Graph |
| `ms_app_client_id` | string | no | Shared Entra client ID for Bot Framework and Graph |
| `ms_app_client_secret` | secret | yes | Shared Entra client secret; write-only in API responses |
| `botframework_scope` | string | no | Default `https://api.botframework.com/.default` |
| `graph_scope` | string | no | Default `https://graph.microsoft.com/.default` |

## `app_settings` model

| Column | Type | Description |
|--------|------|-------------|
| `key` | string (PK) | Setting identifier matching a `Settings` field name |
| `value` | text | Stored value; encrypted when `is_secret` is true |
| `is_secret` | boolean | Whether the value is Fernet-encrypted at rest |
| `updated_at` | datetime | Last modification timestamp |
| `updated_by_id` | string (FK users) | Admin user who last changed the override |

Secret overrides use Fernet encryption. The encryption key is `SETTINGS_ENC_KEY` when set, otherwise derived from `SESSION_SECRET`.

## Admin settings API

All endpoints require admin authentication and `X-CSRF-Token`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/settings` | List overridable settings with env default, effective value, and override state |
| `PUT` | `/api/v1/admin/settings/{key}` | Set or update an override (`{"value": "..."}`) |
| `DELETE` | `/api/v1/admin/settings/{key}` | Remove override and restore environment default |

Changes are recorded in `audit_events` as `settings.override.set` and `settings.override.reset`.

Secret values are write-only: API responses report `configured` or `missing`, never the plaintext value.

## Runtime API surface

The FastAPI app mounts these routers under `API_V1_PREFIX`, which defaults to `/api/v1`.

| Area | Method | Path | Notes |
|------|--------|------|-------|
| Health | `GET` | `/health` | App health response |
| Health | `GET` | `/readyz` | Executes `SELECT 1` against the database |
| Auth | `POST` | `/auth/login` | Issues session cookie and CSRF token |
| Auth | `POST` | `/auth/logout` | Requires CSRF |
| Auth | `GET` | `/sessions/me` | Refreshes CSRF token |
| Admin | `GET` | `/admin/users` | Lists users in the current organization; no create/update user endpoints exist |
| Admin | `GET` | `/admin/readiness` | Bot, Graph, runtime, OAuth and cookie diagnostics |
| Admin | `GET` | `/admin/logs` | Audit events |
| Admin | `GET` | `/admin/system-logs` | Captured Teams bot activity events |
| Webhook routes | `GET` | `/webhook-routes` | Route list |
| Webhook routes | `GET` | `/webhook-routes/defaults` | Route defaults, currently `bot_default_service_url` |
| Webhook routes | `POST` | `/webhook-routes` | Requires CSRF |
| Webhook routes | `PATCH` | `/webhook-routes/{route_id}` | Requires CSRF |
| Webhook routes | `DELETE` | `/webhook-routes/{route_id}` | Requires CSRF |
| Webhook routes | `POST` | `/webhook-routes/{route_id}/test` | Sends a manual test, requires CSRF |
| Webhook routes | `POST` | `/webhook-routes/{route_id}/regenerate-url` | Rotates the relay URL, requires CSRF |
| Webhook routes | `POST` | `/webhook-routes/refresh-graph-names` | Refreshes all stored Graph names, requires CSRF |
| Webhook routes | `POST` | `/webhook-routes/{route_id}/refresh-graph-names` | Refreshes one route, requires CSRF |
| Delivery events | `GET` | `/webhook-routes/{route_id}/deliveries` | Recent deliveries for one route |
| Delivery events | `GET` | `/webhook-delivery-events` | Paginated delivery/event log |
| Delivery events | `GET` | `/webhook-delivery-events/{event_id}` | Delivery/event detail |
| Delivery events | `POST` | `/webhook-delivery-events/cleanup` | Manual log-retention cleanup, requires CSRF |
| Relay ingress | `POST` | `/webhooks/{route_token}` | Public relay URL for source systems |
| Bot | `POST` | `/bot/messages` | Public Teams bot activity ingest |
| Bot | `GET` | `/bot/conversation-references` | Known Bot Framework conversations |
| Graph targets | `GET` | `/teams-targets/search?kind=user\|team&q=...` | Graph-backed user/team search |
| Graph targets | `GET` | `/teams-targets/teams/{team_id}/channels?q=...` | Graph-backed channel listing |

## Teams bot command behavior

`POST /bot/messages` stores bot activity events and upserts conversation references when an activity includes both `serviceUrl` and `conversation.id`. Message activities can also execute slash commands:

| Command | Behavior |
|---------|----------|
| `/register <route name>` | Creates or updates a route for the current conversation and returns the relay URL |
| `/webhook <route name>` | Returns the relay URL for an existing route |
| `/disable [route name]` | Disables a route linked to the current conversation |
| `/enable [route name]` | Enables a route linked to the current conversation |
| `/delete <route name>` | Deletes a route linked to the current conversation |
| `/info [route name]` | Shows captured conversation IDs and linked route details |
| `/help` | Shows available commands |

Bot-created routes use the default organization from `DEFAULT_ORG_SLUG`, `source_system=teams-command`, and `bot_target_source=bot_command`.

## Payload handling

`POST /webhooks/{route_token}` accepts non-empty request bodies up to `WEBHOOK_MAX_PAYLOAD_BYTES`. Payload normalization supports:

- Plain text bodies.
- JSON objects.
- JSON arrays.
- Bot activity objects with Adaptive Card attachments using `application/vnd.microsoft.card.adaptive`.

Rejected payloads, disabled routes, unknown route tokens, failed deliveries, manual tests and successful deliveries are all stored as `webhook_delivery_events`.

## Docker Compose

The backend service loads variables from `.env` via `env_file`. Only `DATABASE_URL` is overridden in `docker-compose.yml` to point at the bundled Postgres service.

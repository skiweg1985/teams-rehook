# Data Model

Teams Rehook uses SQLAlchemy models in `backend/app/models.py`.

The backend creates tables at startup and applies additive/backfill schema handling through `backend/app/seed.py`. No standalone migration framework is present.

## Entities

| Entity | Table | Purpose |
|---|---|---|
| Organization | `organizations` | Tenant-like grouping for users, routes, and settings. |
| User | `users` | Admin users for the UI and private APIs. |
| Session | `sessions` | Session token and CSRF token hashes with expiration/revocation state. |
| WebhookRoute | `webhook_routes` | Route definition, relay token, delivery backend, Teams target metadata, and last-delivery state. |
| WebhookDeliveryEvent | `webhook_delivery_events` | Stored result of delivered, failed, or rejected webhook attempts. |
| BotActivityEvent | `bot_activity_events` | Captured inbound Teams bot activity metadata and sanitized raw activity JSON. |
| BotConversationReference | `bot_conversation_references` | Sendable Bot Framework conversation references captured from Teams activities. |
| GraphDelegatedCredential | `graph_delegated_credentials` | Delegated Graph delivery credential metadata and encrypted refresh material. |
| AuditEvent | `audit_events` | Admin and system audit events. |
| AppSetting | `app_settings` | Persisted admin settings, including environment overrides and application-managed feature switches. |

## Relationships

- `users.organization_id` references `organizations.id`.
- `sessions.user_id` references `users.id`.
- `webhook_routes.organization_id` references `organizations.id`.
- `webhook_routes.created_by_id` references `users.id`.
- `webhook_delivery_events.organization_id` references `organizations.id`.
- `webhook_delivery_events.route_id` references `webhook_routes.id` and may become `NULL` when a route is deleted.
- `graph_delegated_credentials.organization_id` is unique per organization.
- `audit_events.organization_id` optionally references `organizations.id`.
- `app_settings.updated_by_id` optionally references `users.id`.

## Important Fields

### `webhook_routes`

| Field | Notes |
|---|---|
| `name` | Unique per organization and delivery backend. |
| `is_active` | Disabled routes reject incoming relay requests. |
| `route_token_hash` | Hash used for relay URL lookup. |
| `route_token` | Current route token used to build relay URLs. Treat as secret. |
| `delivery_backend` | `bot_framework` or `graph`. |
| `target_name` | Display label for the route target. |
| `bot_service_url`, `bot_conversation_id` | Bot Framework delivery target values. |
| `graph_*` fields | Graph target metadata for lookup, display, and delivery. |
| `member_summary`, `member_count`, `member_list_json`, `members_refreshed_at`, `members_lookup_error` | Best-effort participant metadata for group chat targets. |
| `last_delivery_status`, `last_delivery_at` | Last route delivery outcome summary. |

### `webhook_delivery_events`

| Field | Notes |
|---|---|
| `status` | `delivered`, `failed`, or `rejected`. |
| `request_metadata_json` | Sanitized request metadata. |
| `normalized_message_json` | Normalized message representation. |
| `delivery_result_json` | Delivery backend result metadata. |
| `error` | Error summary when delivery failed or request was rejected. |

### `bot_conversation_references`

Stores Bot Framework values needed to send proactive messages:

- `service_url`
- `conversation_id`
- tenant/team/channel/user metadata
- Graph IDs when available
- best-effort group-chat participant summary, count, limited member list, refresh timestamp, and lookup error
- `last_seen_at`

### `graph_delegated_credentials`

Stores delegated Graph service-user connection metadata:

- tenant/client IDs
- granted scopes
- encrypted refresh token
- service-user identity
- last status/error
- access-token expiration and refresh-check timestamps

The refresh token is secret material and must not be returned in API responses, logs, monitoring output, or documentation.

### `app_settings`

Stores admin-overridden runtime settings:

- `key`
- `value`
- `is_secret`
- `updated_at`
- `updated_by_id`

Secret values are encrypted at rest using `SETTINGS_ENC_KEY`. `SESSION_SECRET` is not used for settings encryption.

## Retention

`LOG_RETENTION_DAYS` and `LOG_CLEANUP_INTERVAL_MINUTES` control cleanup for delivery events, audit events, and bot activity events through `backend/app/services/log_retention.py`.

TODO: Define production retention, compliance, backup, and restore requirements.

## Validation Rules

Important validation rules are implemented in Pydantic schemas and router/service logic:

- Route names are required and limited to 200 characters.
- Route names are unique per organization and delivery backend.
- Bot Framework routes require service URL and conversation ID.
- Graph channel routes require team ID and channel ID.
- Graph chat routes require chat ID.
- Graph delivery requires Graph lookup to remain enabled.
- Webhook request bodies must be non-empty and not exceed `WEBHOOK_MAX_PAYLOAD_BYTES`.

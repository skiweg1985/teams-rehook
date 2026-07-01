# Data Model

Teams Rehook uses SQLAlchemy models in `backend/app/models.py`.

The backend creates tables at startup and applies additive/backfill schema handling through `backend/app/seed.py`. No standalone migration framework is present.

## Entities

| Entity | Table | Purpose |
|---|---|---|
| Organization | `organizations` | Tenant-like grouping for users, routes, and settings. |
| User | `users` | Admin users for the UI and private APIs. |
| BotAccessRole | `bot_access_roles` | Permission bundles for Teams bot command access. |
| BotAuthorizedUser | `bot_authorized_users` | Direct Entra user grants for Teams bot command access. |
| BotAuthorizedGroup | `bot_authorized_groups` | Entra group grants for Teams bot command access. |
| BotUserGroupMembershipCache | `bot_user_group_membership_cache` | Cached transitive group membership checks for Teams bot senders. |
| Session | `sessions` | Session token and CSRF token hashes with expiration/revocation state. |
| WebhookRoute | `webhook_routes` | Route definition, relay token, delivery backend, Teams target metadata, and last-delivery state. |
| WebhookDeliveryEvent | `webhook_delivery_events` | Stored result of delivered, failed, or rejected webhook attempts. |
| WebhookUrlRevealToken | `webhook_url_reveal_tokens` | Temporary hashed tokens used to reveal relay URLs without storing plaintext in links. |
| WebhookAbuseBucket | `webhook_abuse_buckets` | Failure counters and temporary block state for noisy webhook clients. |
| BotActivityEvent | `bot_activity_events` | Captured inbound Teams bot activity metadata and sanitized raw activity JSON. |
| BotConversationReference | `bot_conversation_references` | Sendable Bot Framework conversation references captured from Teams activities. |
| GraphDelegatedCredential | `graph_delegated_credentials` | Delegated Graph delivery credential metadata and encrypted refresh material. |
| GraphDelegatedOAuthPendingCredential | `graph_delegated_oauth_pending_credentials` | Pending delegated Graph OAuth connections awaiting admin confirmation. |
| AuditEvent | `audit_events` | Admin and system audit events. |
| EventLogEntry | `event_log_entries` | Unified operational/security/application event log entries. |
| AppSetting | `app_settings` | Persisted admin settings, including environment overrides and application-managed feature switches. |

## Relationships

- `users.organization_id` references `organizations.id`.
- `bot_access_roles.organization_id` references `organizations.id`.
- `bot_authorized_users.organization_id` references `organizations.id`.
- `bot_authorized_users.role_id` optionally references `bot_access_roles.id`.
- `bot_authorized_groups.organization_id` references `organizations.id`.
- `bot_authorized_groups.role_id` optionally references `bot_access_roles.id`.
- `bot_user_group_membership_cache.organization_id` references `organizations.id`.
- `sessions.user_id` references `users.id`.
- `webhook_routes.organization_id` references `organizations.id`.
- `webhook_routes.created_by_id` references `users.id`.
- `webhook_delivery_events.organization_id` references `organizations.id`.
- `webhook_delivery_events.route_id` references `webhook_routes.id` and may become `NULL` when a route is deleted.
- `webhook_url_reveal_tokens.organization_id` references `organizations.id`.
- `webhook_url_reveal_tokens.route_id` references `webhook_routes.id`.
- `graph_delegated_credentials.organization_id` is unique per organization.
- `graph_delegated_oauth_pending_credentials.organization_id` is unique per organization while a pending connection exists.
- `graph_delegated_oauth_pending_credentials.created_by_id` optionally references `users.id`.
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
| `client_ip_access_mode`, `client_ip_allowlist` | Optional per-route client IP restrictions. Allowlist values are normalized IP addresses or CIDR ranges. |
| `target_name` | Display label for the route target. |
| `bot_service_url`, `bot_conversation_id` | Bot Framework delivery target values. |
| `graph_*` fields | Graph target metadata for lookup, display, and delivery. |
| `member_summary`, `member_count`, `member_list_json`, `members_refreshed_at`, `members_lookup_error` | Best-effort participant metadata for group chat targets. |
| `last_delivery_status`, `last_delivery_at` | Last route delivery outcome summary. |

### `webhook_delivery_events`

| Field | Notes |
|---|---|
| `status` | `delivered`, `failed`, or `rejected`. |
| `idempotency_key` | Optional caller-supplied key used to avoid duplicate delivery for repeated requests to the same route. |
| `request_metadata_json` | Sanitized request metadata. |
| `normalized_message_json` | Normalized message representation. |
| `delivery_result_json` | Delivery backend result metadata. |
| `error` | Error summary when delivery failed or request was rejected. |

### `bot_access_roles`, `bot_authorized_users`, and `bot_authorized_groups`

These tables control Teams bot command access:

- roles store named permission bundles such as view routes, reveal webhook URLs, manage status, delete routes, manage allowlists, and create private-chat or channel routes
- direct user grants store an Entra object ID, display/user principal name, active state, optional role, and effective permissions
- group grants store an Entra group object ID, display/mail/group type metadata, active state, optional role, and effective permissions

System roles are seeded during startup. Custom roles can be created by administrators.

### `bot_user_group_membership_cache`

Caches a Teams sender's resolved group IDs for Bot Access checks. Rows store the Entra user object ID, serialized group IDs, check/expiry timestamps, and the last lookup error.

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

### `graph_delegated_oauth_pending_credentials`

Stores pending delegated Graph OAuth credential material until an administrator confirms or cancels the connection. Pending rows include an expiration timestamp and encrypted refresh token material.

### `webhook_url_reveal_tokens`

Stores temporary reveal links for relay URLs. The database stores only the reveal token hash, organization, route, expiration, and creation timestamp.

### `webhook_abuse_buckets`

Stores webhook abuse tracking state:

- hashed bucket key and client fingerprint
- scope (`ip` or `ip_route`)
- optional route token hash
- failure and block counts
- active abuse window, block expiry, last reason, and last seen timestamp

### `event_log_entries`

Stores unified event log rows with level, category, event type, user-facing message, correlation/request IDs, actor/target/source/http/security metadata, optional raw debug payload, and optional domain linkage.

### `app_settings`

Stores admin-overridden runtime settings:

- `key`
- `value`
- `is_secret`
- `updated_at`
- `updated_by_id`

Secret values are encrypted at rest using `SETTINGS_ENC_KEY`. `SESSION_SECRET` is not used for settings encryption.

When `SESSION_SECRET` or `SETTINGS_ENC_KEY` are omitted, startup stores generated instance values in special `app_settings` rows named `__instance_session_secret` and `__instance_settings_enc_key`.

## Retention

`LOG_RETENTION_DAYS` and `LOG_CLEANUP_INTERVAL_MINUTES` control cleanup for delivery events, audit events, bot activity events, and unified event log entries through `backend/app/services/log_retention.py`.

TODO: Define production retention, compliance, backup, and restore requirements.

## Validation Rules

Important validation rules are implemented in Pydantic schemas and router/service logic:

- Route names are required and limited to 200 characters.
- Route names are unique per organization and delivery backend.
- Bot Framework routes require service URL and conversation ID.
- Graph channel routes require team ID and channel ID.
- Graph chat routes require chat ID.
- Graph delivery requires Graph lookup to remain enabled.
- Restricted client IP routes require at least one valid IP address or CIDR range.
- Webhook request bodies must be non-empty and not exceed `WEBHOOK_MAX_PAYLOAD_BYTES`.
- Valid `Idempotency-Key` headers are limited to 8-120 characters using letters, numbers, `.`, `_`, `:`, or `-`.

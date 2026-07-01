# API Reference

The FastAPI app mounts routes under `API_V1_PREFIX`, which defaults to `/api/v1`.

Interactive docs are available in a running local stack at:

```text
http://localhost:8080/api/v1/docs
```

## Authentication

Admin APIs use session-cookie authentication. Authenticated write requests require `X-CSRF-Token`.

The frontend receives a CSRF token from login and session refresh responses.

## Health

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/health` | Public | Returns service name and version. |
| `GET` | `/api/v1/readyz` | Public | Executes a database `SELECT 1` and returns service name and version. |

## Sessions

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/setup/status` | Public | Reports whether first-run admin setup is required. |
| `POST` | `/api/v1/setup/admin` | Public until setup is complete | Creates the first admin, sets the session cookie, and returns user and CSRF token. |
| `POST` | `/api/v1/auth/login` | Public | Authenticates by email/password, sets session cookie, returns user and CSRF token. |
| `POST` | `/api/v1/auth/logout` | Session + CSRF | Revokes the current session and clears the session cookie. |
| `GET` | `/api/v1/sessions/me` | Session | Returns the current user and refreshes the CSRF token. |

Example login:

```bash
curl -i -X POST "http://localhost:8080/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"your-admin-password"}'
```

## Webhook Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/webhook-routes` | Admin session | List routes for the current organization. |
| `POST` | `/api/v1/webhook-routes` | Admin session + CSRF | Create a route. |
| `PATCH` | `/api/v1/webhook-routes/{route_id}` | Admin session + CSRF | Update a route. |
| `DELETE` | `/api/v1/webhook-routes/{route_id}` | Admin session + CSRF | Delete a route and detach its delivery events. |
| `POST` | `/api/v1/webhook-routes/{route_id}/test` | Admin session + CSRF | Send a manual test message. |
| `POST` | `/api/v1/webhook-routes/{route_id}/regenerate-url` | Admin session + CSRF | Generate a new relay URL and invalidate the old URL. |
| `POST` | `/api/v1/webhook-routes/refresh-graph-names` | Admin session + CSRF | Refresh stored Graph names for routes and references. |
| `POST` | `/api/v1/webhook-routes/{route_id}/refresh-graph-names` | Admin session + CSRF | Refresh Graph names for one route. |
| `POST` | `/api/v1/webhook-routes/{route_id}/refresh-members` | Admin session + CSRF | Refresh participant summary fields for a Bot Framework conversation or Graph chat route. |
| `GET` | `/api/v1/webhook-routes/{route_id}/deliveries` | Admin session | List recent deliveries for one route. |

Route create/update payloads are defined by `WebhookRouteCreate` and `WebhookRouteUpdate` in `backend/app/schemas.py`. Supported delivery backends are `bot_framework` and `graph`.

Route responses include best-effort group-chat participant metadata: `member_summary`, `member_count`, `members`, `members_refreshed_at`, and `members_lookup_error`.

## Public Relay Ingress

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/webhooks/{route_token}` | Route token in URL | Accepts an incoming webhook payload for the matching route. |

Example:

```bash
curl -X POST "YOUR_RELAY_URL" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test alert","message":"Webhook connected successfully","severity":"info"}'
```

The route token is secret. Do not log or publish real relay URLs.

## Delivery Events And Logs

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/webhook-delivery-events` | Admin session | Paginated delivery log with status, route, and search filters. |
| `GET` | `/api/v1/webhook-delivery-events/{event_id}` | Admin session | Delivery event detail. |
| `POST` | `/api/v1/webhook-delivery-events/cleanup` | Admin session + CSRF | Manual delivery/audit/bot activity cleanup. |
| `GET` | `/api/v1/admin/logs` | Admin session + CSRF | Audit events. |
| `GET` | `/api/v1/admin/event-logs` | Admin session + CSRF | Paginated unified event log with level, category, type, correlation/request ID, and search filters. |
| `POST` | `/api/v1/admin/client-events` | Admin session + CSRF | Records a frontend-originated event log entry. |
| `GET` | `/api/v1/admin/system-logs` | Admin session + CSRF | Captured Teams bot activity events. |
| `POST` | `/api/v1/admin/logs/cleanup` | Admin session + CSRF | Manual cleanup endpoint exposed by the admin router. |

## Webhook Abuse Blocking

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/admin/webhook-abuse-buckets` | Admin session + CSRF | List currently blocked clients and clients observed within the active abuse window. |
| `DELETE` | `/api/v1/admin/webhook-abuse-buckets/{bucket_id}` | Admin session + CSRF | Unblock a client and clear its current failure count while keeping escalation history. |
| `POST` | `/api/v1/admin/webhook-abuse-buckets/cleanup` | Admin session + CSRF | Remove inactive abuse tracking buckets older than `WEBHOOK_ABUSE_CLEANUP_DAYS`. |

## Admin Settings And Readiness

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/admin/settings` | Admin session + CSRF | List overridable settings with environment, effective, and override state. Proxy trust ranges that must also be consumed by HAProxy remain environment-only and are not writable here. |
| `PUT` | `/api/v1/admin/settings/{key}` | Admin session + CSRF | Set or update one override. |
| `DELETE` | `/api/v1/admin/settings/{key}` | Admin session + CSRF | Remove one override and restore environment value. |
| `GET` | `/api/v1/admin/readiness` | Admin session + CSRF | Return non-secret Bot, Graph, OAuth, runtime, payload, retention, cookie, and proxy trust diagnostics. |
| `GET` | `/api/v1/admin/users` | Admin session + CSRF | List users in the current organization. |
| `POST` | `/api/v1/admin/users` | Admin session + CSRF | Create a user. |
| `PATCH` | `/api/v1/admin/users/{user_id}` | Admin session + CSRF | Update a user email, display name, role, or active status. |
| `PUT` | `/api/v1/admin/users/{user_id}/password` | Admin session + CSRF | Set a user password. |

Secret setting values are write-only. Responses report configured/missing state, not plaintext.

The readiness runtime payload includes the configured Compose subnet, additional trusted upstream proxies, and the combined effective trust chain used for forwarded client IP resolution.

## Graph Delivery OAuth

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/admin/graph-delivery/oauth/start` | Admin session + CSRF | Build Microsoft authorization URL for delegated Graph delivery. |
| `GET` | `/api/v1/admin/graph-delivery/oauth/callback` | Admin session | OAuth callback that stores delegated Graph credential material. |
| `DELETE` | `/api/v1/admin/graph-delivery/oauth` | Admin session + CSRF | Disconnect delegated Graph delivery. |

The redirect URI is:

```text
{APP_PUBLIC_BASE_URL}/api/v1/admin/graph-delivery/oauth/callback
```

## Bot Messages

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/bot/messages` | Bot Framework bearer token | Receives Teams bot activities, captures conversation references, and handles bot commands. Invalid, missing, expired, mismatched, or incorrectly signed tokens are rejected before persistence. |
| `GET` | `/api/v1/bot/conversation-references` | Admin session | Lists known Bot Framework conversations. |

Accepted bot activities store non-sensitive authentication metadata such as validated issuer, audience, service URL match status and validation time. Raw bearer tokens and full JWTs are never stored. Historical bot activity rows created before auth metadata existed may report `auth_status` as `unknown`.

Captured group-chat references include the same best-effort participant metadata as route responses when the lookup succeeds.

## Teams Targets

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/teams-targets/search?kind=user\|team&q=...` | Admin session | Search Graph users or teams. |
| `GET` | `/api/v1/teams-targets/teams/{team_id}/channels?q=...` | Admin session | List/search channels for a team. |
| `GET` | `/api/v1/teams-targets/chats?q=...` | Admin session | List/search chats for the delegated service user. |

## Machine Monitoring

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/monitoring/status` | Bearer API key | Returns JSON service, database, readiness, route, delivery, rolling-window, and problem-route status. |
| `GET` | `/api/v1/monitoring/prtg` | Bearer API key | Returns PRTG HTTP Data Advanced Sensor JSON derived from the same monitoring status. |

Example:

```bash
curl "http://localhost:8080/api/v1/monitoring/status" \
  -H "Authorization: Bearer <MONITORING_API_KEY>"
```

PRTG HTTP Data Advanced Sensor example:

```bash
curl "http://localhost:8080/api/v1/monitoring/prtg" \
  -H "Authorization: Bearer <MONITORING_API_KEY>"
```

```json
{
  "prtg": {
    "result": [
      {
        "channel": "Service State",
        "value": 0,
        "valuelookup": "prtg.standardlookups.wmi.diskhealth.health"
      },
      {
        "channel": "Database OK",
        "value": 1,
        "unit": "Custom",
        "customunit": "state",
        "valuelookup": "prtg.standardlookups.boolean.statetrueok"
      }
    ],
    "text": "Teams Rehook ok; database ok; routes active=1/1, issues=0; 5m delivered=1, issues=0"
  }
}
```

If `MONITORING_API_KEY` is empty, the endpoint returns `503`. If the bearer token is missing or wrong, it returns `401`.

## Error Behavior

Common response statuses:

| Status | Meaning |
|---:|---|
| `400` | Invalid request body, invalid setting value, invalid route target, or missing OAuth code. |
| `401` | Missing/invalid session or monitoring API key. |
| `403` | Missing admin access or invalid CSRF token. |
| `404` | Unknown setting, route, or delivery event. |
| `409` | Duplicate route name/backend or disabled integration dependency. |
| `413` | Webhook payload exceeds configured size limit. |
| `502` | Upstream Microsoft Graph or delivery request failed. |
| `503` | Required configuration is missing or monitoring API key is not configured. |

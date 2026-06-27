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
| `POST` | `/api/v1/auth/login` | Public | Authenticates by email/password, sets session cookie, returns user and CSRF token. |
| `POST` | `/api/v1/auth/logout` | Session + CSRF | Revokes the current session and clears the session cookie. |
| `GET` | `/api/v1/sessions/me` | Session | Returns the current user and refreshes the CSRF token. |

Example login:

```bash
curl -i -X POST "http://localhost:8080/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"change-me-admin-password"}'
```

## Webhook Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/webhook-routes` | Admin session | List routes for the current organization. |
| `GET` | `/api/v1/webhook-routes/defaults` | Admin session | Returns route defaults such as `bot_default_service_url`. |
| `POST` | `/api/v1/webhook-routes` | Admin session + CSRF | Create a route. |
| `PATCH` | `/api/v1/webhook-routes/{route_id}` | Admin session + CSRF | Update a route. |
| `DELETE` | `/api/v1/webhook-routes/{route_id}` | Admin session + CSRF | Delete a route and detach its delivery events. |
| `POST` | `/api/v1/webhook-routes/{route_id}/test` | Admin session + CSRF | Send a manual test message. |
| `POST` | `/api/v1/webhook-routes/{route_id}/regenerate-url` | Admin session + CSRF | Generate a new relay URL and invalidate the old URL. |
| `POST` | `/api/v1/webhook-routes/refresh-graph-names` | Admin session + CSRF | Refresh stored Graph names for routes and references. |
| `POST` | `/api/v1/webhook-routes/{route_id}/refresh-graph-names` | Admin session + CSRF | Refresh Graph names for one route. |
| `GET` | `/api/v1/webhook-routes/{route_id}/deliveries` | Admin session | List recent deliveries for one route. |

Route create/update payloads are defined by `WebhookRouteCreate` and `WebhookRouteUpdate` in `backend/app/schemas.py`. Supported delivery backends are `bot_framework` and `graph`.

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
| `GET` | `/api/v1/admin/system-logs` | Admin session + CSRF | Captured Teams bot activity events. |
| `POST` | `/api/v1/admin/logs/cleanup` | Admin session + CSRF | Manual cleanup endpoint exposed by the admin router. |

## Admin Settings And Readiness

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/admin/settings` | Admin session + CSRF | List overridable settings with environment, effective, and override state. |
| `PUT` | `/api/v1/admin/settings/{key}` | Admin session + CSRF | Set or update one override. |
| `DELETE` | `/api/v1/admin/settings/{key}` | Admin session + CSRF | Remove one override and restore environment value. |
| `GET` | `/api/v1/admin/readiness` | Admin session + CSRF | Return non-secret Bot, Graph, OAuth, runtime, payload, retention, and cookie diagnostics. |
| `GET` | `/api/v1/admin/users` | Admin session + CSRF | List users in the current organization. |

Secret setting values are write-only. Responses report configured/missing state, not plaintext.

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
| `POST` | `/api/v1/bot/messages` | Public bot ingress | Receives Teams bot activities, captures conversation references, and handles bot commands. |
| `GET` | `/api/v1/bot/conversation-references` | Admin session | Lists known Bot Framework conversations. |

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

Example:

```bash
curl "http://localhost:8080/api/v1/monitoring/status" \
  -H "Authorization: Bearer <MONITORING_API_KEY>"
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

# Teams Rehook User Guide

Teams Rehook relays webhook messages from internal systems into Microsoft Teams. Administrators create stable relay URLs, connect those URLs to captured Teams bot conversations, test delivery, and monitor webhook outcomes from one operations UI.

Teams Rehook is currently an internal MVP/evaluation-stage tool. The core relay flow is implemented, but production rollout still depends on tenant-specific Bot Framework setup, Microsoft Graph permissions, operational ownership, and hardening decisions.

## What Teams Rehook Is For

- Connect webhook sources such as monitoring, firewall events, or operations systems to Teams
- Manage stable relay URLs for external systems and event streams
- Capture Teams bot conversations and use them as delivery targets
- Send test messages before enabling a relay URL in production
- Build plain JSON and Adaptive Card payload examples for external systems
- Review delivered, failed, and rejected webhook attempts
- Regenerate relay URLs when a URL must be rotated or has been exposed

## Prerequisites

- Docker and Docker Compose for the default local stack
- A Teams bot/app registration for real Teams delivery
- Entra app credentials (`MS_APP_*`) for Bot Framework delivery and Microsoft Graph target search
- A Teams chat or channel where the bot is installed and allowed to receive at least one activity

Graph search helps find Teams, channels, and users. It does not prove that the bot can send to that target. A route is sendable only after Teams Rehook has a valid Bot Framework service URL and conversation ID, usually captured from an inbound bot activity.

## Start The Application

1. Copy the example configuration:

   ```bash
   cp .env.example .env
   ```

2. Start the application:

   ```bash
   docker compose up -d --build
   ```

3. Open the application:

   ```text
   http://localhost:8080
   ```

The API documentation is available at `http://localhost:8080/api/v1/docs`.

If port `8080` or `8443` is already in use, update `PROXY_HTTP_PORT` and `PROXY_HTTPS_PORT` in `.env`.

## First Sign-In

On first start, the application creates an admin user from `.env`. The defaults from `.env.example` are:

```text
Email: admin@example.com
Password: change-me-admin-password
```

Change these before production-like use:

```text
BOOTSTRAP_ADMIN_EMAIL=
BOOTSTRAP_ADMIN_PASSWORD=
BOOTSTRAP_ADMIN_DISPLAY_NAME=
SESSION_SECRET=
```

Restart the containers after changing configuration.

## Delivery Modes

Real Teams delivery is the default:

```text
BOT_DELIVERY_MODE=real
MS_APP_TENANT_ID=
MS_APP_CLIENT_ID=
MS_APP_CLIENT_SECRET=
BOT_DEFAULT_SERVICE_URL=
```

Until the Entra credentials are configured, `/api/v1/admin/readiness` reports `ready=false` for bot delivery.

For local validation without sending real Teams messages, set:

```text
BOT_DELIVERY_MODE=mock
```

Mock mode records successful delivery attempts without contacting Bot Framework.

The same Entra app registration credentials are used for Bot Framework delivery and Microsoft Graph target search. API scopes remain separate:

```text
BOTFRAMEWORK_SCOPE=https://api.botframework.com/.default
GRAPH_SCOPE=https://graph.microsoft.com/.default
```

### Microsoft Graph Permissions

Teams Rehook uses Microsoft Graph in two separate ways:

- Graph lookup uses app-only client credentials for target search and display-name resolution.
- Graph delivery uses a delegated service-user connection for Microsoft Graph-backed route delivery.

Configure these Microsoft Graph **Application permissions** on the Entra app registration used by `MS_APP_CLIENT_ID`, then grant tenant admin consent. Teams Rehook requests lookup tokens with the client credentials flow and `GRAPH_SCOPE=https://graph.microsoft.com/.default`.

Graph lookup needs:

- `User.Read.All` for user search and name resolution through `/users` and `/users/{id}`.
- `Team.ReadBasic.All` for team search and name resolution through `/teams` and `/teams/{team-id}`.
- `Channel.ReadBasic.All` for channel lookup and name resolution through `/teams/{team-id}/channels` and `/teams/{team-id}/channels/{channel-id}`.

Settings > Readiness also performs optional read-only diagnostics against `/servicePrincipals` and `/organization` to display the app registration and tenant metadata behind the token. If those diagnostic metadata calls are not available in a tenant, target search can still work as long as the required permissions above are present; the page will show a permission warning for the missing optional metadata.

Configure these Microsoft Graph **Delegated permissions** on the same Entra app registration for Graph delivery, then grant consent as required by the tenant:

- `offline_access` so Teams Rehook can refresh the delegated service-user connection.
- `User.Read` for the delegated sign-in baseline.
- `ChannelMessage.Send` for Graph channel delivery.
- `ChatMessage.Send` for delivery into existing chats.
- `Chat.ReadBasic` for service-user chat search in the route UI.
- `Chat.Create` for creating or linking one-on-one chats when a route targets a selected user.

Add this redirect URI under the app registration's web authentication platform:

```text
{APP_PUBLIC_BASE_URL}/api/v1/admin/graph-delivery/oauth/callback
```

With the local defaults from `.env.example`, the callback URL is:

```text
http://localhost:8080/api/v1/admin/graph-delivery/oauth/callback
```

Graph delivery messages appear in Teams as the connected delegated service user. The service user must be licensed and must already be a member of the selected Teams channels or chats. Teams Rehook does not create 1:1 chats in V1.

If a Graph channel test fails with HTTP 403, `Forbidden`, `InsufficientPrivileges`, or a similar access-denied response, first verify the connected service user shown under **Settings > Status > Graph delivery**. Add that exact user to the target Team/channel, confirm the delegated `ChannelMessage.Send` permission has tenant consent, then run **Send test** again. A channel found by Graph lookup is only selectable metadata; it does not prove the delegated service user can post there.

Use **Settings > Readiness** to verify delivery mode, credential completeness, Bot and Graph token request status, public URLs, payload limits, log retention, and cookie configuration.

## Prepare A Teams Target

1. Install or add the Teams Rehook bot to the target chat or channel.
2. Send the bot a message or mention it in the channel.
3. Open **Webhooks** in Teams Rehook.
4. Click **Known conversations**.
5. Confirm that the target conversation appears in the list.

If the conversation is not listed, Teams Rehook does not yet have a sendable Bot Framework conversation reference. Use the manual delivery target fields only when you already have a valid service URL and conversation ID.

### Teams Bot Commands

Inbound Teams bot messages also capture or refresh the conversation reference. The bot recognizes commands in chats or channels where it is installed:

```text
register <route name>  create or update a route for this Teams conversation
webhook <route name>   show the relay URL for an existing route
disable [route name]   disable a route linked to this conversation
enable [route name]    enable a route linked to this conversation
delete <route name>    delete a route linked to this conversation
info [route name]      show captured IDs and linked route details
help                   show the command list
```

Routes created through `register` still need the same operational care as UI-created routes. Treat the returned relay URL as a secret.

## Create A Webhook Route

1. Open **Webhooks**.
2. Click **New route**.
3. Enter a clear name, for example `PRTG network alerts`.
4. Keep **Route is active** enabled.
5. Select the captured Teams conversation.
6. Click **Create route**.
7. Use **Send test** and confirm that the message appears in Teams.
8. Copy the relay URL into the external system.

After saving, Teams Rehook copies the generated relay URL to your clipboard. You can copy it again from the route table with **Copy URL**.

## Send Webhook Payloads

Teams Rehook accepts plain text, JSON objects, JSON arrays, and Adaptive Card activities with `application/vnd.microsoft.card.adaptive`.

Example JSON payload:

```json
{
  "title": "CPU usage critical",
  "message": "Server app-01 has been above 95 percent for 5 minutes.",
  "severity": "critical",
  "status": "open"
}
```

Quick `curl` test:

```bash
curl -X POST "YOUR_RELAY_URL" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test alert","message":"Webhook connected successfully","severity":"info"}'
```

Empty payloads, invalid JSON, unknown route tokens, disabled routes, and oversized requests are rejected and recorded in **Messages**.

## Build Example Payloads

Open **Payload Generator** to build external-system payload examples without hand-writing JSON. It can generate:

- Plain message JSON with title, message text, severity-style details, and name/value facts.
- Adaptive Card activity JSON with title formatting, optional image, facts, OpenURL buttons, and Teams full-width card metadata.

Use **Copy JSON**, then paste the generated body into the external system or a `curl` test against the route relay URL.

## Operate And Troubleshoot

- **Dashboard** shows route counts, known conversations, failed/rejected routes, inactive routes, and untested active routes.
- **Webhooks** manages routes, relay URLs, test sends, Graph name refresh, and known conversations.
- **Payload Generator** builds text and Adaptive Card JSON examples for relay testing.
- **Users** lists the bootstrap or existing users known to the current organization. User invitation and user editing flows are not implemented in the current UI.
- **Messages** shows delivery logs with filters for status, route, and search text.
- **System logs** shows sign-ins, route changes, admin activity, and Teams bot activity events.
- **Settings > Readiness** shows non-secret configuration state for Bot, Graph, OAuth token checks, runtime URLs, payload limits, retention, cleanup, and secure-cookie behavior.

Logs are retained for `LOG_RETENTION_DAYS` days, defaulting to 7.

## Rotate Or Disable A Relay URL

- **Copy URL** copies the current relay URL.
- **Regenerate relay URL** creates a new URL and immediately invalidates the old one.
- Disable a route when it should stop accepting messages but remain available for later.
- Delete a route only when the connection is no longer needed. Incoming requests to the old URL will fail.

Treat relay URLs as secrets. Anyone with a valid relay URL can send messages to the connected Teams conversation.

## Common Setup Blockers

**No known conversations**

Add the bot to the target Teams chat or channel and send or mention it once. Graph search alone does not create a sendable target.

**Route test fails in real mode**

Check Entra app credentials, bot installation in the target conversation, and whether the selected service URL/conversation ID matches the expected Teams context.

**Teams targets are not found**

Check Entra app credentials and Microsoft Graph permissions, or rely on already captured bot conversations. Graph may require tenant admin consent.

**Webhook requests are rejected**

Check that the route is active, the relay URL is current, the payload is non-empty, and the request does not exceed `WEBHOOK_MAX_PAYLOAD_BYTES`.

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

The Vite development server proxies `/api` to the port in `PROXY_HTTP_PORT` from the root `.env`, defaulting to `8080`. When running the backend directly on Uvicorn's default port `8000` without HAProxy, set `PROXY_HTTP_PORT=8000` in `.env` or start the backend on the configured proxy port. If the frontend calls the backend directly from another origin, keep `CORS_ORIGINS` aligned with the Vite development server origin.

Validation:

```bash
npm run test
```

Useful individual checks from the repository root:

```bash
npm run frontend:build
npm run backend:check
npm run backend:test
```

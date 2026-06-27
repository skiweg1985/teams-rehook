# User Guide

## What Teams Rehook Is

Teams Rehook is a relay service for sending webhook messages into Microsoft Teams. External systems send to stable relay URLs. Teams Rehook validates the route, normalizes the payload, sends the message to the configured Teams target, and records the outcome.

The application is designed for operational notifications such as monitoring alerts, firewall events, infrastructure signals, and other internal event streams.

## Who Uses It

Typical users are operators and administrators who need to connect an external system to a Teams chat or channel without exposing Microsoft Teams delivery details to every source system.

Developers and maintainers use the technical API and data model documentation instead:

- [Developer guide](developer-guide.md)
- [API reference](api.md)
- [Architecture](architecture.md)

## Problems It Solves

- External systems can keep using a stable webhook URL.
- Teams targets can be changed centrally in the relay.
- Operators can test routes before sharing the URL.
- Failed, rejected, and delivered messages are visible in one UI.
- Relay URLs can be rotated when they are exposed or need to be replaced.

## Basic Concepts

| Term | Meaning |
|---|---|
| Webhook route | A named mapping from one relay URL to one Teams delivery target. |
| Relay URL | The route-specific URL that external systems call. Treat it as a secret. |
| Teams target | A Bot Framework conversation or Graph-backed chat/channel target. |
| Known conversation | A Teams bot conversation reference captured from an inbound bot activity. |
| Delivery event | A stored record of a delivered, failed, or rejected webhook attempt. |
| Readiness | Non-secret operational checks for credentials, URLs, limits, and integrations. |

## First Steps

1. Sign in with an administrator account.
2. Open **Settings > Readiness** and check whether the intended delivery backend is ready.
3. Add the Teams Rehook bot to the target Teams chat or channel.
4. Send or mention the bot once so Teams Rehook can capture the conversation reference.
5. Open **Webhooks** and check **Known conversations**.
6. Create a route for the target conversation.
7. Use **Send test**.
8. Copy the relay URL into the external system.

Graph search can help find Teams, channels, users, and chats. A Graph search result does not prove that the bot or delegated Graph service user can send there. Always validate with **Send test**.

## Creating A Webhook Route

1. Open **Webhooks**.
2. Click **New route**.
3. Enter a clear name, for example `PRTG network alerts`.
4. Keep the route active unless it should be staged but not used yet.
5. Select a captured Teams conversation or supported Graph target.
6. Save the route.
7. Send a test message.
8. Copy the relay URL into the source system.

The generated relay URL is copied after creation and can be copied again from the route table.

## Sending Payloads

Teams Rehook accepts:

- Plain text request bodies.
- JSON objects.
- JSON arrays.
- Bot activity objects with Adaptive Card attachments using `application/vnd.microsoft.card.adaptive`.

Example JSON body:

```json
{
  "title": "CPU usage critical",
  "message": "Server app-01 has been above 95 percent for 5 minutes.",
  "severity": "critical",
  "status": "open"
}
```

Example `curl` test:

```bash
curl -X POST "YOUR_RELAY_URL" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test alert","message":"Webhook connected successfully","severity":"info"}'
```

Empty payloads, invalid JSON, unknown route tokens, disabled routes, and oversized requests are rejected and recorded in **Messages**.

## Payload Generator

Open **Payload Generator** to build example webhook bodies without writing JSON manually. It can generate:

- Plain message JSON with title, message text, severity-style details, and facts.
- Adaptive Card activity JSON with title formatting, optional image, facts, OpenURL buttons, and Teams full-width card metadata.

Use **Copy JSON**, then paste the generated body into an external system or a `curl` test.

## Teams Bot Commands

Inbound Teams bot messages capture or refresh the conversation reference. The bot recognizes these commands in chats or channels where it is installed:

| Command | Behavior |
|---|---|
| `register <route name>` | Create or update a route for the current Teams conversation. |
| `webhook <route name>` | Show the relay URL for an existing route. |
| `disable [route name]` | Disable a route linked to this conversation. |
| `enable [route name]` | Enable a route linked to this conversation. |
| `delete <route name>` | Delete a route linked to this conversation. |
| `info [route name]` | Show captured IDs and linked route details. |
| `help` | Show available commands. |

Routes created through `register` still need the same operational care as UI-created routes. Treat returned relay URLs as secrets.

## Monitoring What Happened

- **Dashboard** shows route counts, known conversations, failed/rejected routes, inactive routes, and untested active routes.
- **Webhooks** manages routes, relay URLs, tests, Graph name refresh, and known conversations.
- **Messages** shows delivery logs with filters for status, route, and search text.
- **System logs** shows sign-ins, route changes, admin activity, and Teams bot activity events.
- **Settings > Readiness** shows non-secret configuration and integration status.

## Limits

- Teams Rehook is currently an MVP/evaluation-stage tool.
- The Users page lists known users, but user invitation, editing, role management, and password reset flows are not implemented in the current UI.
- Real Teams delivery depends on tenant-specific Microsoft Teams bot installation, Entra credentials, Graph permissions, and captured or resolved delivery targets.
- Graph lookup is target metadata. It is not a sendability guarantee.
- No dedicated queue/retry worker is visible in the repository.

## FAQ

### Why is no known conversation listed?

Add the bot to the target Teams chat or channel and send or mention it once. Teams Rehook needs a Bot Framework service URL and conversation ID before a Bot Framework route can send.

### Why does a route test fail in real mode?

Check Entra app credentials, bot installation, delivery backend selection, and whether the stored service URL or Graph target matches the expected Teams context.

### Why are webhook requests rejected?

Common causes are an inactive route, an outdated relay URL, an empty payload, invalid JSON, an unknown route token, or a payload larger than `WEBHOOK_MAX_PAYLOAD_BYTES`.

### Who should I contact for support?

TODO: Add project support or ownership contact.

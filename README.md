# Teams Messenger User Guide

Teams Messenger relays webhook messages from internal systems into Microsoft Teams. Administrators create stable relay URLs, connect those URLs to Teams conversations, and review whether messages were delivered successfully.

## What Teams Messenger Is For

- Connect webhook sources such as monitoring, firewall events, or operations systems to Teams
- Manage one stable relay URL per source
- Select Teams targets from known bot conversations
- Send test messages before enabling a source in production
- Review delivered, failed, and rejected webhook attempts
- Regenerate relay URLs when a URL must be rotated or has been exposed

## Start The Application

1. Copy the example configuration:

   ```bash
   cp .env.example .env
   ```

2. Start the application:

   ```bash
   docker compose up -d --build
   ```

3. Open the application in your browser:

   ```text
   http://localhost:8080
   ```

The API documentation is available at `http://localhost:8080/api/v1/docs`.

If you need different ports, update `PROXY_HTTP_PORT` and `PROXY_HTTPS_PORT` in `.env`.

## First Sign-In

On first start, the application creates an admin user from `.env`. The default values from `.env.example` are:

```text
Email: admin@example.com
Password: change-me-admin-password
```

Change these values before production use:

```text
BOOTSTRAP_ADMIN_EMAIL=
BOOTSTRAP_ADMIN_PASSWORD=
BOOTSTRAP_ADMIN_DISPLAY_NAME=
SESSION_SECRET=
```

Restart the containers after changing configuration.

## Prepare Teams Targets

A webhook route needs a Teams conversation where the bot is allowed to send messages. The easiest setup is to use a conversation the bot has already seen.

1. Install or add the Teams bot to the target conversation.
2. Send the bot a message or mention it in the target channel.
3. Open **Webhooks** in Teams Messenger.
4. Click **Known conversations** to review captured conversations.

If the conversation is not listed yet, use the advanced target fields when creating a route and enter the Bot Framework details manually:

- Teams target name
- Bot service URL
- Bot conversation ID

## Create A Webhook Route

1. Open **Webhooks**.
2. Click **New route**.
3. Enter a clear name, for example `PRTG network alerts`.
4. Optionally enter the source system, for example `PRTG`, `macmon`, or `firewall-events`.
5. Make sure **Route is active** is enabled.
6. Select the target under **Teams conversation**.
7. Click **Create route**.

After saving, Teams Messenger generates a relay URL. The URL is copied to your clipboard automatically. You can also copy it later from the route table with **Copy URL**.

## Use The Webhook URL In A Source System

Add the generated relay URL as the webhook target in your source system. Treat the URL as a secret: anyone who has it can send messages to the connected Teams conversation.

Teams Messenger accepts text and JSON payloads. For JSON, known fields are normalized into a Teams message, for example:

```json
{
  "title": "CPU usage critical",
  "message": "Server app-01 has been above 95 percent for 5 minutes.",
  "severity": "critical",
  "status": "open"
}
```

A quick `curl` test looks like this:

```bash
curl -X POST "YOUR_RELAY_URL" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test alert","message":"Webhook connected successfully","severity":"info"}'
```

Supported inputs:

- plain text
- JSON objects
- JSON arrays
- Adaptive Card activities with `application/vnd.microsoft.card.adaptive`

Empty or invalid payloads are rejected and recorded in the logs.

## Test A Route

Test every route before using it in production.

1. Open **Webhooks**.
2. Find the route.
3. Click **Send test** in the actions column.
4. Confirm that the test message arrived in Teams.
5. Open **View delivery logs** if you need delivery details.

The status in the route table shows whether the last delivery was delivered, failed, or rejected.

## Review Deliveries

Open **Messages** to inspect webhook and test messages.

You can filter the view by:

- status: `Delivered`, `Failed`, `Rejected`
- route
- search text, such as source, message, error, or payload content

Select a log entry to see details such as the normalized message, request metadata, error text, and bot delivery response.

Logs are kept for 7 days by default. Configure this with `LOG_RETENTION_DAYS` in `.env`.

## Copy Or Rotate A Relay URL

The route table provides two important URL actions:

- **Copy URL** copies the current relay URL.
- **Regenerate relay URL** creates a new URL for the same route.

When a URL is regenerated, the old URL stops working immediately. Update every source system that still uses the old URL.

## Disable, Edit, Or Delete A Route

- Disable a route when it should stop accepting messages but remain available for later.
- Edit a route when the name, source system, or Teams target changes.
- Delete a route only when the connection is no longer needed. Incoming requests to the old URL will fail.

## Users And System Logs

The **Users** page shows known users, roles, and account status.

The **System logs** page shows administrative activity such as sign-ins, route changes, and system events. Use **Clean up** to remove old log entries according to the retention period.

## Delivery Modes

Local validation uses mock delivery by default:

```text
BOT_DELIVERY_MODE=mock
```

In this mode, deliveries are simulated and no real Teams messages are sent.

For real Teams delivery, set the mode to `real` and configure Bot Framework credentials:

```text
BOT_DELIVERY_MODE=real
BOT_TENANT_ID=
BOT_CLIENT_ID=
BOT_CLIENT_SECRET=
BOT_DEFAULT_SERVICE_URL=
```

If Microsoft Graph should be used for target search and name resolution, optionally configure separate Graph credentials. If left empty, the application attempts to reuse the bot app registration:

```text
GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=
```

## Troubleshooting

**Sign-in fails**

Check `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`, and `SESSION_SECRET` in `.env`. Restart the containers after making changes.

**A route is rejected**

Check that the route is active, the relay URL is correct, and the request sends a non-empty payload.

**Delivery fails**

Check the error text in **Messages**. Common causes are invalid bot credentials, an incorrect conversation value, or missing bot permissions in the Teams conversation.

**Teams targets are not found**

Check the Microsoft Graph configuration or use the manual target fields when creating the route.

**A relay URL was exposed**

Open the route and use **Regenerate relay URL**. Then update all legitimate source systems with the new URL.

## Local Development

To run the backend and frontend without Docker:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

When frontend and backend run separately, keep `CORS_ORIGINS` aligned with the Vite development server origin.

To validate the project:

```bash
npm run test
```

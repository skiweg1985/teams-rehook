# Feature Matrix

Status values:

- ✅ Available
- 🧪 Experimental
- ⚙️ Administrative
- 🔐 Security relevant
- ❓ Unclear / to verify

| Area | Feature | Status | Description | Audience |
|---|---|---|---|---|
| 💬 Messaging / Communication | Relay URLs | ✅ Available | Each webhook route has a stable relay URL for external systems. | Users, administrators |
| 💬 Messaging / Communication | Bot Framework delivery | ✅ Available | Sends normalized messages to stored Teams Bot Framework conversation references. | Users, administrators |
| 💬 Messaging / Communication | Delegated Graph delivery | ✅ Available | Sends Graph-backed routes through a delegated service-user connection for supported channel and chat targets. | Administrators |
| 💬 Messaging / Communication | Group chat participant summaries | ✅ Available | Shows best-effort participant summaries for captured Bot Framework group chats and refreshable Graph chat routes. | Users, administrators |
| 💬 Messaging / Communication | Test sends | ✅ Available | Operators can send a test message for a configured route before sharing the relay URL. | Users, administrators |
| 💬 Messaging / Communication | Teams bot commands | ✅ Available | The bot handles `register`, `webhook`, `enable`, `disable`, `delete`, `info`, and `help`. | Users, administrators |
| 🧩 Integrations | Webhook payload normalization | ✅ Available | Accepts plain text, JSON objects, JSON arrays, and Adaptive Card activity payloads. | Users, developers |
| 🧩 Integrations | Payload Generator | ✅ Available | Builds example text and Adaptive Card JSON payloads in the UI. | Users |
| 🧩 Integrations | Microsoft Graph target lookup | ✅ Available | Searches users, teams, channels, and service-user chats when Graph credentials are configured. | Administrators |
| 🔐 Security | Session authentication | 🔐 Security relevant | Admin UI and private APIs require authenticated sessions. | Administrators, developers |
| 🔐 Security | CSRF protection | 🔐 Security relevant | Authenticated write requests require `X-CSRF-Token`. | Developers |
| 🔐 Security | Relay URL rotation | 🔐 Security relevant | Regenerating a route URL immediately invalidates the previous URL. | Administrators |
| 🔐 Security | Secret masking | 🔐 Security relevant | Secret settings are write-only in API responses and UI diagnostics. | Administrators |
| ⚙️ Administration | Runtime settings overrides | ⚙️ Administrative | Selected settings can be overridden in the database through the admin settings API/UI. | Administrators |
| ⚙️ Administration | Readiness diagnostics | ⚙️ Administrative | Reports non-secret Bot, Graph, runtime, OAuth, payload, retention, and cookie state. | Administrators |
| ⚙️ Administration | User management | ✅ Available | Admins can create users, edit access state and roles, and set passwords. | Administrators |
| 📊 Monitoring | Delivery event log | ✅ Available | Records successful, failed, and rejected webhook attempts with normalized metadata. | Users, administrators |
| 📊 Monitoring | Audit and system logs | ✅ Available | Records admin actions and captured Teams bot activity events. | Administrators |
| 📊 Monitoring | Machine monitoring endpoint | ✅ Available | Provides API-key protected JSON status at `/api/v1/monitoring/status`. | Administrators |
| 📊 Monitoring | Prometheus/OpenMetrics | ❓ Unclear / to verify | The repository documents this as a future follow-up, not an implemented endpoint. | Administrators |
| 🧪 Testing | Mock delivery mode | 🧪 Experimental | Simulates successful delivery without contacting Bot Framework. | Developers, administrators |
| 🛠️ Developer Functions | Full validation script | ✅ Available | `npm run test` builds the frontend, checks backend syntax, and runs pytest. | Developers, maintainers |
| 🛠️ Developer Functions | Dedicated migration tool | ❓ Unclear / to verify | Startup code creates and backfills schema, but no standalone migration framework is present. | Developers, maintainers |

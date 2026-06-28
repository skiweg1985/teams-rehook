# PRD: Teams Rehook

## 1. Context / Problem

Existing Microsoft Teams Incoming Webhooks and Office 365 Connector webhooks are not a reliable long-term integration path for operational notifications. Teams Workflows and Power Automate can also be hard to operate for this use case because they are often tied to user-owned identities or ownership models.

Teams Rehook addresses this with a service-operated relay model: source systems send to stable relay URLs while Teams targets are managed centrally in the relay service.

Relevant source systems may include monitoring tools, firewall events, network tools, and other operations systems.

## 2. Product Goal

Teams Rehook should provide a centrally operated Teams webhook relay service.

The product goal is to provide:

- Central webhook ingestion.
- Stable relay URLs for source systems.
- Central management of webhook-to-Teams target mappings.
- A service-owned operating model rather than a user-owned target architecture.
- Traceable logging for acceptance, routing, delivery, and rejection.
- Safe relay URL rotation.
- A focused operations UI for setup, tests, readiness, and failure analysis.

## 3. Current Status

Teams Rehook is an implemented MVP in evaluation status. The core flow exists:

```text
source webhook -> relay URL -> route -> configured Teams target -> delivery test/logs
```

Implemented capabilities:

- FastAPI backend with SQLAlchemy, sessions, CSRF protection, and first-run admin setup.
- Docker Compose stack with Postgres, backend, frontend, and HAProxy.
- Authenticated admin UI with Dashboard, Webhooks, Payload Generator, Messages, Users, Settings, and System logs.
- Stable relay URLs per webhook route.
- Relay URL regeneration with immediate invalidation of old URLs.
- Active/inactive state per route.
- Payload Generator for text and Adaptive Card example payloads.
- Bot conversation capture from inbound Teams bot activities.
- Teams bot commands for route registration, URL lookup, enable/disable, delete, info, and help.
- Selection of known Teams bot conversations when creating routes.
- Manual fallback fields for Bot Framework service URL and conversation ID.
- Microsoft Graph search and name resolution for Teams targets when configured.
- Graph delivery through a delegated service-user connection for supported Graph targets.
- Mock delivery mode for local validation.
- Real delivery mode through Bot Framework credentials or per-route Graph delivery configuration.
- Delivery logs with normalized payload, request metadata, delivery response, and errors.
- Log retention and manual cleanup.
- Settings and readiness views for non-secret runtime, credential, token, integration, payload, retention, and cookie state.
- API-key protected JSON monitoring status for external polling systems.

## 4. Target Audiences

- Administrators managing relay routes and Teams targets.
- Operations teams checking webhook delivery and failures.
- Project owners evaluating whether Teams Rehook is suitable as a standard path for Teams notifications.
- Developers and maintainers extending or operating the codebase.

## 5. Functional Requirements

Teams Rehook must:

- Accept incoming webhook requests through route-specific URLs.
- Reject unknown, disabled, empty, invalid, or oversized requests in a controlled way.
- Accept text bodies, JSON objects, JSON arrays, and Adaptive Card activity payloads.
- Normalize payloads into an internal message format.
- Manage webhook routes with name, delivery backend, active state, Teams target, and relay URL.
- Generate, copy, and rotate relay URLs.
- Capture Teams bot conversations from inbound bot activities.
- Make known conversations selectable as route targets.
- Allow manual target configuration when a valid Bot Framework conversation reference is already known.
- Use Graph target search and Graph name resolution when Graph credentials are available.
- Communicate that Graph target metadata is not proof of sendability.
- Generate example payloads for plain messages and Adaptive Card activities.
- Provide Teams bot commands for route-adjacent administration from an installed Teams context.
- Send test messages per route.
- Log delivered, failed, and rejected attempts.
- Show dashboard signals for failed, rejected, inactive, and untested routes.
- Show readiness for Bot Framework, Graph lookup, Graph delivery, OAuth token checks, runtime URLs, payload limits, and log retention.
- Provide an API-key protected JSON monitoring endpoint with rolling delivery windows for `5m`, `15m`, and `1h`.

## 6. Non-Functional Requirements

- Bot credentials, client secrets, route tokens, and conversation IDs must not be unnecessarily exposed in the UI or logs.
- Readiness output must expose only configuration and health state, not secret values, tokens, headers, or raw authentication responses.
- Monitoring output must not include relay URLs, route tokens, Bot service URLs, conversation IDs, OAuth tokens, secrets, or raw authentication responses.
- Session-changing and administrative requests must remain protected against CSRF.
- Mock mode must allow local tests without real Teams delivery.
- Real mode must clearly report missing credentials as not ready.
- Logs must have bounded retention and a cleanup path.
- The UI should remain scan-friendly and task-focused for repeated operator work.
- Existing source systems should only need to change their target URL where possible.

## 7. Architecture Summary

Teams Rehook follows a relay model:

1. A source system sends a webhook request to a relay URL.
2. The backend finds the route through the secret route token hash.
3. Route state and payload are validated.
4. The payload is normalized.
5. Mock mode simulates delivery.
6. Real mode sends through Bot Framework or Microsoft Graph, depending on route backend.
7. The result is stored as a delivery event.

Microsoft Graph is used for lookup, display-name resolution, and Graph delivery routes. Graph search results do not guarantee send permission; every route should be validated with **Send test**.

The V1 monitoring endpoint is JSON/status oriented and meant for external polling systems. Prometheus/OpenMetrics output is a future follow-up.

## 8. MVP Acceptance Criteria

The MVP is suitable for further evaluation when:

- The application starts locally with Docker Compose.
- An admin can sign in and manage routes.
- At least one Teams bot conversation can be captured or manually configured.
- A webhook route can be created and tested.
- A real or simulated delivery is logged.
- Rejected and failed requests are visible with an error cause.
- Relay URLs can be copied and rotated.
- Dashboard and empty states guide operators to the next useful action.
- Settings show readiness for Bot, Graph, token, and runtime configuration without secrets.
- A monitoring system can detect delivery degradation through the JSON status endpoint without UI scraping.
- README and documentation describe the current product state consistently.

## 9. Known Limitations

- The MVP is not yet a complete production operations platform.
- High availability, backup/restore, monitoring, alerting, and SLOs still need to be defined.
- The organization model is minimal and evaluation-oriented.
- The Users page supports lightweight administrator-managed creation, editing, status changes, role changes, and password resets.
- Graph permissions and tenant admin consent must be clarified per tenant.
- Graph search results are not a guarantee of Bot Framework or Graph delivery sendability.
- The bot must be installed in the target context and provide a valid conversation reference for Bot Framework routes.
- Not all historical incoming webhook payloads are guaranteed to map one-to-one.
- Secret rotation, operations ownership, and support model must be finalized before production.

## 10. Open Product Questions

- Which source systems should migrate first?
- Which Teams contexts may be used as targets?
- Which Graph permissions are acceptable for the organization?
- What retention and audit requirements apply in production?
- Who owns Teams Rehook operationally after evaluation?
- Is a queue/retry model needed for temporary Teams, Graph, or Bot Framework failures?

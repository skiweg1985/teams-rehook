# Graph Delivery Variant A

## Purpose

This note defines the Variant A delivery model for Microsoft Graph delivery in
Teams Rehook. It is the architecture output for GitHub issue #4 and is intended
to unblock the backend auth, delivery, readiness and frontend work in issues #7,
#8, #9 and #10.

Variant A means normal operational sending through Microsoft Graph as a
parallel route backend. It does not replace Bot Framework delivery, and it does
not use Microsoft Graph migration/import APIs as the product's normal send path.

## Current Repo State

Teams Rehook currently has two separate Microsoft integration surfaces:

- Bot Framework delivery sends webhook messages to captured Teams conversation
  references. Real delivery requires a Bot Framework `service_url` and
  `conversation_id`.
- Microsoft Graph is used for lookup and display-name resolution. The current
  Graph token flow uses `MS_APP_*` client credentials with
  `GRAPH_SCOPE=https://graph.microsoft.com/.default`.

The README currently describes this correctly: Graph access is optional and only
supports target search and name resolution; Teams delivery itself still uses Bot
Framework credentials plus captured Teams conversation references.

## Microsoft Graph Delivery Constraints

Primary Microsoft references:

- Send chatMessage in a channel or chat:
  https://learn.microsoft.com/en-us/graph/api/chatmessage-post?view=graph-rest-1.0
- Create chat:
  https://learn.microsoft.com/en-us/graph/api/chat-post?view=graph-rest-1.0
- Microsoft Graph permissions reference:
  https://learn.microsoft.com/en-us/graph/permissions-reference

Important constraints for this product:

- Sending a `chatMessage` to a Teams channel uses
  `POST /teams/{team-id}/channels/{channel-id}/messages`.
- Sending a `chatMessage` to a Teams chat uses
  `POST /chats/{chat-id}/messages`.
- Microsoft's `chatMessage` send API lists delegated work or school
  permissions for normal channel/chat sends.
- The application permission shown on the send API is `Teamwork.Migrate.All`,
  and Microsoft marks application permissions there as migration-only. This is
  not a normal operational sending model for Teams Rehook.
- The response sender identity is a Teams user identity. For Variant A, the
  visible sender is therefore the delegated service user, not the Teams Rehook
  bot.
- Microsoft Graph supports chat creation with `POST /chats`; creating a 1:1 chat
  returns the existing chat when one already exists between the same members.
  Chat creation is a separate workflow from sending to a known `chat_id`.

## V1 Target Support Decision

| Target type | V1 decision | Required route identifiers | Delivery endpoint | Delegated permissions |
| --- | --- | --- | --- | --- |
| Team channel | Supported first | `team_id`, `channel_id` | `POST /teams/{team-id}/channels/{channel-id}/messages` | `ChannelMessage.Send` |
| Existing group chat | Supported for chats the service user belongs to | `chat_id` | `POST /chats/{chat-id}/messages` | `ChatMessage.Send`; `Chat.ReadBasic` for service-user chat search |
| User / 1:1 | Supported in V1 via route-setup chat resolution/creation | `chat_id` once resolved or created | `POST /chats/{chat-id}/messages` | `ChatMessage.Send`; `Chat.Create` for route setup resolving/creating the 1:1 chat |

V1 should not treat a Graph user ID alone as a sendable delivery target. A user
selection is used during route setup, where Teams Rehook resolves or creates
the one-on-one chat via `Chat.Create` and stores the resulting `chat_id` for
later delivery.

## Delegated Service-User Model

Graph delivery uses a delegated work or school account that acts as the sender
for Graph-backed routes. This account should be an operational service user
owned by the tenant, for example a monitored notification sender account.

Operational rules:

- The service user must be licensed and allowed to send in the selected Teams
  chats/channels.
- Messages appear in Teams as sent by the delegated service user.
- Admins must understand this identity before enabling Graph-backed routes.
- The delegated token/refresh material must be stored as secret material and
  must never be returned in API responses, readiness payloads, delivery logs or
  audit logs.
- App-only Graph lookup credentials remain separate from delegated Graph
  delivery credentials.

Minimum delegated permission set for V1:

- `offline_access` so Teams Rehook can refresh the delegated service-user
  connection.
- `User.Read` as the delegated sign-in baseline.
- `ChannelMessage.Send` for channel routes.
- `ChatMessage.Send` for existing chat routes.
- `Chat.ReadBasic` for listing existing chats that the delegated service user
  belongs to.
- `Chat.Create` for one-on-one route setup so Teams Rehook can resolve or
  create the chat target before later message delivery.

The Entra app registration must also include this web redirect URI:

```text
{APP_PUBLIC_BASE_URL}/api/v1/admin/graph-delivery/oauth/callback
```

With the local `.env.example` defaults, that is:

```text
http://localhost:8080/api/v1/admin/graph-delivery/oauth/callback
```

## Route Metadata

Downstream route modeling should introduce an explicit backend selector and keep
existing Bot Framework fields intact.

Minimum route metadata:

- `delivery_backend`: `bot_framework` or `graph`.
- `graph_target_kind`: one of `channel`, `chat`, or `user`.
- `chat_id`: required for `chat` delivery and for a resolved 1:1 user route.
- `team_id`: required for channel delivery.
- `channel_id`: required for channel delivery.
- Existing display metadata such as target name, team name and channel name for
  UI readability.

Compatibility rules:

- Existing routes default to `delivery_backend = bot_framework`.
- `target_type` can remain for compatibility while delivery routing moves to
  `delivery_backend`.
- Graph-backed routes should validate backend-specific identifiers before
  sending.

## Readiness Requirements

Settings > Readiness should distinguish three concepts:

- Bot delivery readiness: current Bot Framework credential and mode checks.
- Graph lookup readiness: current app-only Graph client credentials used for
  search and display-name resolution.
- Graph delivery readiness: delegated service-user configuration, token
  availability, token freshness and expected delegated permissions.

Graph delivery readiness should report non-secret states only:

- `missing`: delegated delivery has not been configured.
- `expired`: delegated token material exists but cannot currently produce a
  usable access token.
- `permission_warning`: delegated auth works, but required send scopes are not
  visible in diagnostics.
- `ready`: delegated auth works and expected send scopes are present.

The UI should make it clear when a route depends on delegated Graph delivery
prerequisites instead of Bot Framework prerequisites.

## Deferred Follow-Ups

These are explicitly out of scope for Variant A V1:

- Using Microsoft Graph migration/import APIs for normal delivery.
- Treating `Teamwork.Migrate.All` as a production delivery permission.
- Generic tenant-wide app-only Graph sending.
- Resource-specific consent send permissions such as
  `ChannelMessage.Send.Group` or `ChatMessage.Send.Chat`.
- Full Adaptive Card parity between Bot Framework activities and Graph
  `chatMessage` payloads.

RSC/app-only options can be evaluated later as a separate delivery mode if a
tenant wants app-style sender behavior instead of delegated service-user sender
behavior.

## Downstream Issue Guidance

Issue #7 should build delegated Graph auth separately from the existing app-only
Graph lookup token manager. It should expose only safe diagnostics to readiness.

Issue #8 should implement a Graph delivery service that accepts normalized
messages and backend-specific route identifiers. It should start with channel
delivery and add existing chat delivery once route setup can provide `chat_id`.

Issue #9 should split readiness into Bot delivery, Graph lookup and Graph
delivery without leaking tokens or provider error bodies.

Issue #10 should present Bot Framework and Microsoft Graph as explicit backend
choices. For Graph routes, the UI must show the delegated sender prerequisite and
must not imply that a raw user ID is directly sendable.

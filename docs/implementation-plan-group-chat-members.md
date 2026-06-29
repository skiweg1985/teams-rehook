# Group Chat Member Summaries Implementation Plan

GitHub issue: https://github.com/skiweg1985/teams-rehook/issues/50

## Goal

Captured Teams group chats should be distinguishable in Known Conversations and route creation. Instead of displaying every unnamed group chat as `Group chat`, the app should show a best-effort participant summary. Graph chat routes should expose the same summary when an administrator refreshes the route member list.

## Approach

1. Use the existing Bot Framework credentials to call `GET {serviceUrl}/v3/conversations/{conversationId}/members` for captured chat references.
2. Store a privacy-conscious display summary, member count, refresh timestamp, and lookup error on `bot_conversation_references`.
3. Refresh chat members best-effort during bot ingest and when listing known conversations if the summary is missing or stale.
4. Prefer the member summary for Known Conversation titles and generated bot route names.
5. Add a route-level `Refresh members` action for Bot Framework routes and Graph chat routes.
6. For Graph chat routes, use the delegated service-user connection to call Microsoft Graph `GET /chats/{chat-id}/members`.
7. Preserve `Group chat` as fallback if the lookup fails or returns no usable names.

## Permissions

Bot-captured conversation summaries use the Bot Framework Connector API and the app's existing `https://api.botframework.com/.default` token flow. They do not require additional Microsoft Graph scopes.

Graph chat route refresh uses the existing delegated Graph delivery connection. Microsoft Graph documents `Chat.ReadBasic` as the least-privileged delegated work/school permission for listing chat members, and that scope is already part of `DEFAULT_DELEGATED_GRAPH_SCOPES`.

# Graph Target Lookup Notes

## Status

Microsoft Graph target lookup is implemented with app-only credentials. This keeps the relay service aligned with the service-owned operating model and avoids coupling route administration to a personal Microsoft 365 user session.

The Graph lookup is only target discovery metadata for now. Bot delivery still uses the configured Bot Framework service URL and conversation ID, and each route must be validated with a test message before it is treated as reachable.

## Required Configuration

```text
MS_APP_TENANT_ID=
MS_APP_CLIENT_ID=
MS_APP_CLIENT_SECRET=
BOTFRAMEWORK_SCOPE=https://api.botframework.com/.default
GRAPH_SCOPE=https://graph.microsoft.com/.default
```

The same Entra app registration credentials are used for Bot Framework delivery and Graph lookup. API scopes remain separate.

## Starting Permissions

- `User.Read.All` for user search.
- `Team.ReadBasic.All` for Teams search.
- `Channel.ReadBasic.All` for channel listing.

Admin consent is expected for the app-only permissions.

Settings readiness also tries optional read-only metadata checks against `/servicePrincipals` and `/organization` so operators can see which app registration and tenant are behind the token. Missing optional metadata should produce a readiness warning, not block Graph target search when the starting permissions above are present.

## Implemented API Surface

- `GET /api/v1/teams-targets/search?kind=user|team&q=...`
- `GET /api/v1/teams-targets/teams/{team_id}/channels?q=...`
- `POST /api/v1/webhook-routes/refresh-graph-names`
- `POST /api/v1/webhook-routes/{route_id}/refresh-graph-names`

Responses use one shape:

```json
{
  "kind": "channel",
  "id": "channel-id",
  "display_name": "Alerts",
  "subtitle": "standard",
  "team_id": "team-id",
  "team_name": "Operations",
  "channel_id": "channel-id"
}
```

## Open Microsoft Questions

- Whether the existing Teams app/bot is installed in each selected target context.
- Whether a selected Graph channel can be turned into a Bot Framework conversation reference without prior bot installation or interaction.
- Whether proactive installation or proactive conversation creation should be added later, and which Teams app installation permissions would be acceptable for that path.

## References

- Microsoft Graph list users: https://learn.microsoft.com/en-us/graph/api/user-list
- Microsoft Graph list teams: https://learn.microsoft.com/en-us/graph/api/teams-list
- Microsoft Graph list channels: https://learn.microsoft.com/en-us/graph/api/channel-list
- Microsoft Graph service app authentication: https://learn.microsoft.com/en-us/graph/auth-v2-service
- Teams proactive bot messages: https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages

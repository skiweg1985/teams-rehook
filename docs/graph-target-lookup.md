# Graph Target Lookup Notes

## Status

Microsoft Graph target lookup is implemented with app-only credentials. This keeps the relay service aligned with the service-owned operating model and avoids coupling route administration to a personal Microsoft 365 user session.

Graph lookup is target discovery metadata and is also used for Bot Access group search/member lookup. Graph delivery is implemented separately through a delegated service-user connection. Every route must still be validated with a test message before it is treated as reachable.

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
- `Group.Read.All` for Bot Access group search.
- `User.Read.All` plus `GroupMember.Read.All` for resolving a Teams sender's transitive group memberships during Bot Access authorization and for viewing transitive group members.

Admin consent is expected for the app-only permissions.

`Directory.Read.All` can be used instead of the narrower user/group/member read permissions when the tenant prefers one broader directory-read app permission, but the narrower permissions above are the intended baseline.

If group search returns `Microsoft Graph request failed with HTTP 403` and `Authorization_RequestDenied`, the Entra app registration usually lacks `Group.Read.All` or tenant admin consent has not been granted after adding it. If Bot Access group authorization or the group member view fails while direct user search works, verify `User.Read.All` and `GroupMember.Read.All` or `Directory.Read.All`.

Settings readiness also tries optional read-only metadata checks against `/servicePrincipals` and `/organization` so operators can see which app registration and tenant are behind the token. Missing optional metadata should produce a readiness warning, not block Graph target search when the starting permissions above are present.

## Implemented API Surface

- `GET /api/v1/teams-targets/search?kind=user|team|group&q=...`
- `GET /api/v1/teams-targets/teams/{team_id}/channels?q=...`
- `GET /api/v1/teams-targets/groups/{group_id}/members?offset=0&limit=100`
- `GET /api/v1/teams-targets/groups/{group_id}/members/count`
- `GET /api/v1/teams-targets/chats?q=...`
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
- Tenant-specific approval for Graph permissions and delegated service-user operating model.

## References

- Microsoft Graph list users: https://learn.microsoft.com/en-us/graph/api/user-list
- Microsoft Graph list teams: https://learn.microsoft.com/en-us/graph/api/teams-list
- Microsoft Graph list channels: https://learn.microsoft.com/en-us/graph/api/channel-list
- Microsoft Graph list groups: https://learn.microsoft.com/en-us/graph/api/group-list
- Microsoft Graph user transitive memberships: https://learn.microsoft.com/en-us/graph/api/user-list-transitivememberof
- Microsoft Graph service app authentication: https://learn.microsoft.com/en-us/graph/auth-v2-service
- Teams proactive bot messages: https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages

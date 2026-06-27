# Troubleshooting

| Symptom | Possible Cause | Diagnosis | Solution |
|---|---|---|---|
| Application does not start in Docker | Missing or invalid `.env` values | Run `docker compose logs -f backend` | Copy `.env.example` to `.env` and replace required placeholders. |
| Frontend opens but API calls fail | Proxy port mismatch or backend not healthy | Check `docker compose ps` and `docker compose logs proxy backend` | Confirm `PROXY_HTTP_PORT`, backend health, and HAProxy routing. |
| Browser session fails after login | Session cookie or CORS mismatch | Check browser network response and backend logs | Align `CORS_ORIGINS`, `FRONTEND_BASE_URL`, and `SESSION_SECURE_COOKIE` with the actual URL scheme. |
| Authenticated write returns `403` | Missing or stale CSRF token | Check request headers for `X-CSRF-Token` | Refresh session through the UI or call `GET /api/v1/sessions/me` and retry with the returned token. |
| No known Teams conversations | Bot has not sent an activity to Teams Rehook | Check **System logs** and `/bot/conversation-references` | Add the bot to the Teams chat/channel and send or mention it once. |
| Route creation fails with Bot Framework target error | Missing service URL or conversation ID | Check the selected target fields | Use a captured known conversation or provide valid manual Bot Framework values. |
| Route test fails in real mode | Missing Microsoft credentials, wrong target, or bot not installed | Check **Settings > Readiness** and route delivery logs | Configure `MS_APP_*`, verify bot installation, and retest the route. |
| Graph target search returns errors | Graph lookup disabled, missing credentials, or missing Graph permissions | Check Settings readiness and API error response | Enable Graph lookup, configure `MS_APP_*`, grant required Microsoft Graph application permissions and admin consent. |
| Graph delivery returns access denied | Delegated service user lacks access or permission | Check delivery event error and Graph delivery readiness | Add the connected service user to the target channel/chat and verify delegated scopes such as `ChannelMessage.Send` or `ChatMessage.Send`. |
| Monitoring endpoint returns `503` | `MONITORING_API_KEY` is empty | Call `/api/v1/monitoring/status` and inspect status | Set `MONITORING_API_KEY` and restart/reload configuration as needed. |
| Monitoring endpoint returns `401` | Missing or wrong bearer token | Check `Authorization` header | Use `Authorization: Bearer <MONITORING_API_KEY>`. |
| Webhook request returns not found | Unknown or rotated route token | Check whether the route URL was regenerated | Update the external system with the current relay URL. |
| Webhook request is rejected | Disabled route, empty payload, invalid JSON, or oversized body | Check **Messages** for rejected delivery events | Enable the route, fix the payload, or adjust `WEBHOOK_MAX_PAYLOAD_BYTES`. |
| Old relay URL stopped working | Route URL was regenerated | Check route audit events | Replace old URLs in external systems. Regeneration invalidates old URLs immediately. |
| Logs disappear sooner than expected | Retention cleanup is configured aggressively | Check `LOG_RETENTION_DAYS` and Settings | Increase retention if operational policy allows it. |
| Docker Postgres has no previous data | Volume missing or stack recreated with a new volume | Run `docker volume ls` | Restore from backup if available. TODO: Define production restore process. |

## Common Commands

View running containers:

```bash
docker compose ps
```

Follow backend logs:

```bash
docker compose logs -f backend
```

Check repository validation:

```bash
npm run test
```

Run backend tests only:

```bash
npm run backend:test
```

## When To Escalate

Escalate to a maintainer or operator when:

- Microsoft tenant permissions are unclear.
- Real Teams delivery fails despite passing local validation.
- Secret material may have been committed or exposed.
- A relay URL has been shared with the wrong audience.
- Production backup, restore, or rollback is required.

TODO: Add support and escalation contact.

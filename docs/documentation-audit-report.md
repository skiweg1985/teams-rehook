# Documentation Audit Report

Audit date: 2026-06-26

## Scope

Reviewed repository documentation and documentation-like files:

- `AGENTS.md`
- `README.md`
- `docs/CHANGELOG.md`
- `docs/prd-teams-webhook-relay-service.md`
- `docs/technical_documentation.md`
- `docs/graph-autocomplete-spike.md`
- `planning/coordination/WORKLOG.md`

Compared documentation against the current FastAPI routers, settings model, frontend navigation/API client, Docker Compose stack, HAProxy config, package scripts, and `.env.example`.

## Files modified

- `AGENTS.md`
  - Updated the backend syntax-check command to include `backend/app/services/*.py`, matching `package.json`.
- `README.md`
  - Added the implemented Payload Generator.
  - Added implemented Teams bot commands.
  - Clarified Users page limitations.
  - Clarified local Vite proxy behavior when running frontend and backend separately.
  - Added root-level validation commands.
- `docs/technical_documentation.md`
  - Added the verified list of overridable runtime settings and validation constraints.
  - Added the implemented runtime API surface.
  - Added Teams bot command behavior.
  - Added payload handling behavior.
- `docs/prd-teams-webhook-relay-service.md`
  - Added Payload Generator and Teams bot commands as implemented MVP capabilities.
  - Marked the current Users UI as list-only.
- `docs/CHANGELOG.md`
  - Added documentation-audit entries.
  - Noted the Graph lookup document rename.
- `docs/graph-target-lookup.md`
  - Renamed from `docs/graph-autocomplete-spike.md`.
  - Reframed from spike language to implemented Graph lookup notes.
  - Added Graph name-refresh endpoints.
- `docs/documentation-audit-report.md`
  - Added this audit report.

## Obsolete documents or content removed

- Renamed the obsolete spike-named document `docs/graph-autocomplete-spike.md` to `docs/graph-target-lookup.md`.
- Removed or replaced wording that implied Graph target lookup was only a spike.
- Replaced stale backend syntax-check documentation that omitted service modules.

No documentation file was deleted outright. `planning/coordination/WORKLOG.md` was left unchanged because it is a dated historical worklog rather than current-state documentation.

## Dead links and obsolete examples

- External Microsoft Learn links in the Graph lookup document were checked and resolved successfully.
- No broken internal Markdown links were found.
- OAuth scope strings such as `https://graph.microsoft.com/.default` and `https://api.botframework.com/.default` are configuration values, not documentation links; HTTP checks against them are not meaningful.
- Localhost URLs in README depend on the stack running and were not treated as external dead links.

## Remaining documentation gaps

- There is no production operations runbook for backup/restore, monitoring, alerting, SLOs, incident response, or operational ownership.
- There is no tenant-specific Microsoft Teams app/bot registration guide or app manifest in the repository.
- There is no documented secret rotation procedure for `SESSION_SECRET`, `SETTINGS_ENC_KEY`, `MS_APP_CLIENT_SECRET`, route tokens, or Bot Framework credentials.
- The Users page is list-only in the current implementation. There is no user invitation, creation, deactivation, role-management, or password-reset workflow to document from code.
- The frontend calls `POST /api/v1/admin/logs/cleanup`, but the backend exposes `POST /api/v1/webhook-delivery-events/cleanup`. This appears to be an implementation mismatch, not a documentation issue; the technical documentation now records the backend route as implemented.
- There is no database migration documentation or migration tooling visible in the repository; tables are created from SQLAlchemy metadata during startup.

## Could not verify from code alone

- Whether the Entra app registration has the required Microsoft Graph application permissions and admin consent in the target tenant.
- Whether the Bot Framework app is installed in each target Teams chat or channel.
- Whether real Teams delivery works in a specific tenant; the code path exists, but successful delivery depends on tenant configuration and captured conversation references.
- Production public URLs, HTTPS termination details outside local HAProxy, and secure-cookie policy for the eventual deployment.
- Long-term retention, audit, compliance, ownership, and support requirements.

# Documentation Audit Report

## 2026-07-02 Audit Pass

Full documentation audit against the current repository implementation. Code, schemas, routers, models, settings, package scripts, Compose files, HAProxy config, frontend navigation/API usage, and local markdown links were treated as verification sources.

### Files Modified

- `docs/api.md`: added missing Bot Access admin endpoints, delegated Graph OAuth pending endpoints, Bot conversation detail/refresh/delete endpoints, Teams group member endpoints, webhook URL reveal endpoint, PRTG monitoring endpoint examples, idempotency-key behavior, and route client IP access fields; corrected the default interactive docs URL to the recommended HTTPS local profile.
- `docs/data-model.md`: added missing tables for Bot Access roles/users/groups, group membership cache, webhook URL reveal tokens, abuse buckets, pending delegated Graph OAuth credentials, unified event log entries, and generated instance secret rows stored in `app_settings`.
- `docs/configuration.md`: removed `botframework_scope` and `graph_scope` from the admin runtime override table and documented that `BOTFRAMEWORK_SCOPE` and `GRAPH_SCOPE` are environment-only in the current code.
- `docs/admin-guide.md`: replaced stale "Delivery page" wording, added Bot Access operation notes, and changed the environment-change restart command to `./manage.sh restart`.
- `docs/architecture.md`: added the PRTG monitoring endpoint and corrected the stale claim that user management was list-only.
- `docs/feature-matrix.md`: added per-route client IP allowlists, Bot Access controls, and PRTG monitoring coverage.
- `docs/user-guide.md`: documented client IP route restrictions and Bot Access permissions at a user-facing level.
- `docs/graph-target-lookup.md`: updated current status and implemented endpoint list for group member and service-user chat lookup.
- `docs/graph-delivery-variante-a.md`: marked the document as a historical decision note and corrected local redirect URI/profile wording.
- `docs/implementation-plan-group-chat-members.md`: marked the implementation plan as completed/historical.
- `docs/index.md`: labeled historical reference notes accordingly.
- `docs/deployment.md`: corrected the default API docs URL to the recommended HTTPS local profile.
- `CHANGELOG.md`: recorded this documentation audit pass.

### Obsolete Documents Or Content Removed / Marked

- `docs/graph-delivery-variante-a.md` is retained as a historical decision note because it contains useful design rationale, but it no longer presents itself as current operational documentation.
- `docs/implementation-plan-group-chat-members.md` is retained as a completed historical implementation plan.
- `docs/technical_documentation.md` and `docs/CHANGELOG.md` remain compatibility pointers to canonical docs and were not expanded.
- `planning/coordination/WORKLOG.md` still references the removed `docs/graph-autocomplete-spike.md`; it was left unchanged as a dated worklog entry rather than current documentation.

### Remaining Documentation Gaps

- License information is still undefined.
- Security contact, supported versions, triage ownership, response windows, severity levels, and disclosure process remain undefined.
- Production backup/restore schedule, restore validation, retention/compliance requirements, rollout/rollback procedure, hosting platform, TLS/HSTS policy, monitoring/alerting, and operational ownership remain undefined.
- Release versioning, tagging, changelog ownership, and the decision about a formal database migration tool remain undefined.
- There is no tenant-specific Microsoft setup runbook beyond permissions, redirect URI, and delegated service-user prerequisites.

### Could Not Be Verified From Code Alone

- Microsoft tenant permissions, admin-consent policy, and real Microsoft Teams/Bot Framework/Graph behavior in a live tenant.
- Whether the listed Graph permissions are acceptable for a specific organization.
- Production public URLs, TLS termination, secret manager, backup tooling, support contacts, and operational ownership.
- The intended license and security reporting channel.

## 2026-06-29 Audit Pass

Full review of documentation against the current codebase, treating the code as the source of truth.

### Files Modified

- `README.md`: corrected the post-setup access URL to `https://localhost:8443` for the recommended `local` profile, documented the setup profiles, and expanded the `./manage.sh` command list.
- `docs/configuration.md`: added the `event_debug_previews_enabled` runtime override and `EVENT_DEBUG_PREVIEWS_ENABLED` environment variable, both previously undocumented.
- `docs/api.md`: added the previously undocumented admin endpoints `GET /admin/event-logs`, `POST /admin/client-events`, and the `webhook-abuse-buckets` list/reset/cleanup endpoints.
- `docs/admin-guide.md`: corrected install/access URLs to the HTTPS `local` profile, documented setup profiles, clarified the OAuth redirect URI per profile, and referenced `./manage.sh backup-db` / `restore-db`.
- `docs/developer-guide.md`: corrected the local access URL and documented setup profiles.
- `docs/deployment.md`: documented setup profiles and the HTTPS `local` default, and added `restore-db` / `rotate-db-password` to common commands.
- `CHANGELOG.md`: added documentation-audit entry under `[Unreleased]`.

### Verified Correct (No Change Needed)

- API surface in `docs/api.md` otherwise matches `backend/app/routers` (health, sessions, webhook routes, public ingress, settings, readiness, users, graph-delivery OAuth, bot messages, teams targets, monitoring).
- Data model in `docs/data-model.md` matches `backend/app/models.py` entities and relationships.
- Configuration defaults match `backend/app/core/config.py` and `.env.example`.
- Compose service layout, ports, and proxy trust behavior match `docker-compose.yml` and `haproxy/haproxy.cfg`.
- `docs/technical_documentation.md` and `docs/CHANGELOG.md` remain valid compatibility pointers.

### Remaining Gaps

- Production-readiness items remain open `TODO:` markers (license, security contact, supported versions, backup/restore policy, hosting/TLS, release process, migration tool decision). These are intentional and cannot be resolved from code.
- `planning/coordination/WORKLOG.md` references the pre-rename `docs/graph-autocomplete-spike.md`; left unchanged as a dated historical worklog entry.

### Could Not Be Verified From Code Alone

- Microsoft tenant permissions, consent model, and real delivery behavior (require a live tenant).
- Production deployment target, public URLs, and operational ownership.

## 2026-06-27 Audit Pass

Audit date: 2026-06-27

## Scope

Reviewed documentation and documentation-like sources:

- `README.md`
- `.env.example`
- `docs/*.md`
- `AGENTS.md`
- `package.json`
- `frontend/package.json`
- `backend/requirements.txt`
- `docker-compose.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `haproxy/haproxy.cfg`
- FastAPI routers, schemas, settings, models, services, and tests under `backend/app` and `backend/tests`
- Frontend API client and types under `frontend/src`

## Decisions Applied

- Documentation language: English.
- Repository visibility assumption: potentially public.
- Documentation orientation: combined user, administrator, developer, and maintainer documentation.
- Security posture: no internal hostnames, production URLs, customer data, private IP structures, real tokens, or tenant-specific secrets documented.

## Consolidation Performed

- README was shortened into a repository landing page.
- Detailed user workflows moved to [User guide](user-guide.md).
- Runtime and operations guidance moved to [Admin guide](admin-guide.md), [Configuration](configuration.md), [Deployment](deployment.md), and [Troubleshooting](troubleshooting.md).
- API route details moved to [API reference](api.md).
- SQLAlchemy model details moved to [Data model](data-model.md).
- Technical architecture details moved to [Architecture](architecture.md).
- `docs/technical_documentation.md` and `docs/CHANGELOG.md` now point to canonical documents to avoid duplicate sources of truth.

## Corrected Or Removed Content

- Removed the long-form user/admin guide from README.
- Avoided publishing real tenant-specific Microsoft values or production deployment assumptions.
- Kept `.env.example` placeholder-only.
- Marked missing production decisions as `TODO:` rather than inventing them.

## Remaining TODOs

- Add license information.
- Add security contact address.
- Define supported versions and security update policy.
- Define production support and escalation contact.
- Define production hosting, TLS, reverse proxy, and public URL policy.
- Define backup, restore, retention, monitoring, alerting, rollout, and rollback processes.
- Decide whether to introduce a formal database migration tool.
- Define release versioning and changelog ownership.

## Manual Review Recommended

- Security contact and vulnerability reporting channel.
- License choice.
- Production deployment target and public URLs.
- Microsoft tenant permissions and consent model.
- Backup and restore expectations.
- Supported versions and release process.
- Operational ownership and support path.

## Security Review

No real secrets were intentionally copied into documentation. Placeholder values such as `change-me` and localhost URLs remain for local setup examples.

Documentation now treats relay URLs, session secrets, Microsoft client secrets, monitoring API keys, bootstrap passwords, route tokens, and delegated Graph credential material as sensitive.

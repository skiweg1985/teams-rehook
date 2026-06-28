# Documentation Audit Report

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

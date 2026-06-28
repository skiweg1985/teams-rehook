# Changelog

All notable changes to this project are documented here.

This project follows the structure of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Guided `./manage.sh setup` flow that writes a small local `.env` with ports, URLs, bundled Postgres credentials, real delivery defaults, and the session cookie flag.
- Repository documentation restructure with a short README and detailed `/docs` guides for users, administrators, developers, APIs, architecture, configuration, deployment, troubleshooting, and data models.
- Documentation audit report covering updated files, obsolete content, remaining gaps, and manual-review items.
- README coverage for the Payload Generator, Teams bot commands, Users page limitations, and local Vite proxy behavior.
- Admin settings API and UI for runtime overrides with per-field reset to environment defaults.
- `app_settings` table for persisted overrides; secrets encrypted at rest.
- Technical documentation for configuration layers and the settings API contract.
- Activate or deactivate webhook routes directly from the route list.

### Changed

- Compose network CIDR is now controlled through `COMPOSE_APP_SUBNET`, the backend always trusts that internal HAProxy hop by default, and the status view reports the effective proxy trust chain for operators.
- The bundled HAProxy now drops untrusted incoming `X-Forwarded-For` headers and only preserves forwarded chains from upstream proxies explicitly listed in `TRUSTED_PROXY_IPS`.
- Abuse-blocking settings now show only the on/off switch, failure limit, and abuse window in the admin UI; initial block, max block, and cleanup retention move to environment-only configuration.
- `./manage.sh` now uses a consistent CLI output style with structured status messages, stronger destructive-action confirmations, clearer command help, and setup/doctor flows that better guide operators toward the next safe step.
- `./manage.sh setup` now captures listener ports separately from the published app URL, asks for the publish scheme explicitly, and only adds a public URL port when operators want one.
- `./manage.sh setup` now starts with a recommended local-defaults path so the common case only needs a few confirmations; custom ports, HTTP-only mode, and the fixed `app` password remain available when explicitly selected.
- `./manage.sh setup` now generates a random bundled Postgres password by default; the fixed `app` password is only used when explicitly selected.
- `./manage.sh start` now launches the guided setup when `.env` is missing, avoids rebuilding when the Compose stack is already running, and prints the known URLs instead.
- `./manage.sh setup` now offers to start the stack after writing `.env`, but skips that prompt when the Compose stack is already running.
- `.env.example` now keeps only the core infrastructure defaults active; Microsoft identity and most runtime overrides stay commented and are intended to be configured through the Settings UI.
- `bot_delivery_mode` is now an environment-only developer override instead of a runtime setting exposed in the admin UI.
- Runtime overrides can now update `cors_origins` and `session_secure_cookie`, and CORS/session behavior follows effective settings without restarting the backend.
- README is now a concise repository landing page instead of a full user guide.
- Detailed operational, user, API, and architecture content moved under `/docs`.
- Known Teams conversations modal condensed into compact single-row entries showing the channel or user, the involved user, and a relative last-seen time; technical conversation ID, service URL, and Graph IDs removed.
- Webhook route edit modal widened and the name field paired with the status control on one row to reduce vertical scrolling.
- Webhook route active state in the edit modal switched from a checkbox to an Active/Disabled segmented control matching the rest of the UI.
- Webhook route name in the route list is now clickable to open the edit modal.
- Webhook route last-delivery time shown as toned text instead of a status badge in the route list.
- Webhook routes table rows slimmed down: removed the duplicated target name, moved technical Graph IDs into a tooltip, and dropped the bot-source badge.
- Webhook route source-system metadata removed from the route API, forms, delivery logs, and payload normalization.
- `docker-compose.yml` backend `environment` block reduced to the Postgres `DATABASE_URL` override; other variables come from `.env` via `env_file`.
- `.env.example` no longer sets `DATABASE_URL`; local SQLite remains the code default and Docker Compose overrides Postgres.
- Settings page combines editable runtime overrides with integration readiness diagnostics.
- Settings overrides grouped by area with field descriptions, units, monospace technical values, an active-override counter, dirty-state save, and inline reset to default.
- Webhook route actions consolidated into an overflow menu; route list and edit modal visuals unified.
- Dashboard metric cards redesigned with icons, context lines, tabular figures, and a four-column responsive grid; the "Needs attention" card highlights in a warning tone when problems exist.
- Default bot delivery mode changed from `mock` to `real`; set `BOT_DELIVERY_MODE=mock` for credential-free local validation.
- Entra app credentials are configured through `MS_APP_TENANT_ID`, `MS_APP_CLIENT_ID`, and `MS_APP_CLIENT_SECRET` for both Bot Framework delivery and Microsoft Graph lookup.
- Removed separate `BOT_*` and `GRAPH_*` credential variables and the Graph-to-Bot credential fallback.
- Readiness diagnostics now report `credential_source=ms_app` instead of separate bot/graph/inherited sources.
- Renamed the Graph autocomplete spike note to a Graph target lookup implementation note.

### Security

- Documentation now consistently treats relay URLs, Microsoft credentials, monitoring API keys, session secrets, route tokens, and delegated Graph refresh material as secret or sensitive values.

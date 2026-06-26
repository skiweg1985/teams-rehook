# Changelog

## [Unreleased]

### Added

- Documentation audit report covering updated files, removed obsolete content, remaining gaps and manual-review items.
- README coverage for the Payload Generator, Teams bot commands, Users page limitations and local Vite proxy behavior.
- Admin settings API and UI for runtime overrides with per-field reset to environment defaults.
- `app_settings` table for persisted overrides; secrets encrypted at rest.
- Technical documentation for configuration layers and the settings API contract.
- Activate or deactivate webhook routes directly from the route list.

### Changed

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

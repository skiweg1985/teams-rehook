# Changelog

## [Unreleased]

### Added

- Admin settings API and UI for runtime overrides with per-field reset to environment defaults.
- `app_settings` table for persisted overrides; secrets encrypted at rest.
- Technical documentation for configuration layers and the settings API contract.

### Changed

- `docker-compose.yml` backend `environment` block reduced to the Postgres `DATABASE_URL` override; other variables come from `.env` via `env_file`.
- `.env.example` no longer sets `DATABASE_URL`; local SQLite remains the code default and Docker Compose overrides Postgres.
- Settings page combines editable runtime overrides with integration readiness diagnostics.
- Settings overrides grouped by area with field descriptions, units, monospace technical values, an active-override counter, dirty-state save, and inline reset to default.

- Default bot delivery mode changed from `mock` to `real`; set `BOT_DELIVERY_MODE=mock` for credential-free local validation.
- Entra app credentials are configured through `MS_APP_TENANT_ID`, `MS_APP_CLIENT_ID`, and `MS_APP_CLIENT_SECRET` for both Bot Framework delivery and Microsoft Graph lookup.
- Removed separate `BOT_*` and `GRAPH_*` credential variables and the Graph-to-Bot credential fallback.
- Readiness diagnostics now report `credential_source=ms_app` instead of separate bot/graph/inherited sources.

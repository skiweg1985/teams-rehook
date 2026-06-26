# Changelog

## [Unreleased]

### Changed

- Default bot delivery mode changed from `mock` to `real`; set `BOT_DELIVERY_MODE=mock` for credential-free local validation.
- Entra app credentials are configured through `MS_APP_TENANT_ID`, `MS_APP_CLIENT_ID`, and `MS_APP_CLIENT_SECRET` for both Bot Framework delivery and Microsoft Graph lookup.
- Removed separate `BOT_*` and `GRAPH_*` credential variables and the Graph-to-Bot credential fallback.
- Readiness diagnostics now report `credential_source=ms_app` instead of separate bot/graph/inherited sources.

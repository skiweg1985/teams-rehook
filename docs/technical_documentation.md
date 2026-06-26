# Technical documentation

## Configuration layers

Runtime settings are resolved in two layers:

1. **Environment defaults** — loaded from `.env` / process environment via `Settings` in `backend/app/core/config.py`.
2. **Database overrides** — optional per-key values in the `app_settings` table, managed through the admin API and UI.

`get_effective_settings()` merges environment defaults with active overrides. Resetting an override deletes the database row and restores the environment value.

Infrastructure-bound settings (`DATABASE_URL`, `CORS_ORIGINS`, session cookie configuration, bootstrap credentials) remain environment-only and require a process restart when changed.

## `app_settings` model

| Column | Type | Description |
|--------|------|-------------|
| `key` | string (PK) | Setting identifier matching a `Settings` field name |
| `value` | text | Stored value; encrypted when `is_secret` is true |
| `is_secret` | boolean | Whether the value is Fernet-encrypted at rest |
| `updated_at` | datetime | Last modification timestamp |
| `updated_by_id` | string (FK users) | Admin user who last changed the override |

Secret overrides use Fernet encryption. The encryption key is `SETTINGS_ENC_KEY` when set, otherwise derived from `SESSION_SECRET`.

## Admin settings API

All endpoints require admin authentication and `X-CSRF-Token`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/settings` | List overridable settings with env default, effective value, and override state |
| `PUT` | `/api/v1/admin/settings/{key}` | Set or update an override (`{"value": "..."}`) |
| `DELETE` | `/api/v1/admin/settings/{key}` | Remove override and restore environment default |

Changes are recorded in `audit_events` as `settings.override.set` and `settings.override.reset`.

Secret values are write-only: API responses report `configured` or `missing`, never the plaintext value.

## Docker Compose

The backend service loads variables from `.env` via `env_file`. Only `DATABASE_URL` is overridden in `docker-compose.yml` to point at the bundled Postgres service.

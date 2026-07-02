# Operational Hardening Runbook

This runbook defines repository-level operating procedures for keeping Teams Rehook predictable to build, update, recover, and rotate. It intentionally avoids environment-specific contacts, secrets, tenant IDs, and production-only assumptions.

## Scope

Use this runbook for:

- Dependency and lockfile updates.
- Container image digest updates.
- Credential and relay URL rotation.
- Build and deployment verification.
- Rollback and recovery after a failed update.

Keep environment-specific details in the deployment platform or private operations notes, not in this repository.

## Dependency Update Flow

1. Start from the current `dev-1` branch.
2. Review the dependency update PR and confirm the changed files are limited to the expected manifest, lockfile, Dockerfile, or Compose image reference.
3. Confirm package and image updates respect the configured release-age policy.
4. For backend Python updates, keep direct requirements in `backend/requirements.in` and regenerate `backend/requirements.txt` with hashes.
5. For frontend updates, keep `frontend/package-lock.json` as the install source and use `npm ci`.
6. Run validation before merge:

```bash
npm run test
docker compose config
docker compose build backend frontend proxy
docker compose pull postgres
```

7. Review audit and image-scan output. Document any temporary exception in the repo file used by the relevant scan, including an expiry date and a recheck condition.
8. Merge only after CI is green.

## Lockfile And Digest Verification

For backend dependencies:

```bash
cd backend
pip install --require-hashes -r requirements.txt
```

The install must fail if a dependency is missing a hash or a downloaded artifact does not match its recorded hash.

For frontend dependencies:

```bash
cd frontend
npm ci
npm audit
```

`npm ci` must use `package-lock.json` without rewriting dependency resolution during installation.

For container images:

```bash
docker compose config
docker compose build backend frontend proxy
docker compose pull postgres
```

Dockerfile and Compose image references should remain pinned as `tag@sha256:digest`.

## Credential Rotation

Rotate credentials when a secret is exposed, a maintainer changes, a deployment is rebuilt from unknown local state, or the configured rotation interval is reached.

Treat these values as sensitive:

- `SESSION_SECRET`
- `SETTINGS_ENC_KEY`
- `MS_APP_CLIENT_SECRET`
- `MONITORING_API_KEY`
- Database credentials
- Generated relay URLs
- Stored delegated Graph refresh material

General rotation steps:

1. Take a database backup.
2. Generate the replacement credential in the target secret store or `.env` management flow.
3. Update the application configuration.
4. Restart the affected services.
5. Confirm `/api/v1/health` and `/api/v1/readyz`.
6. Test one authenticated admin workflow and one webhook delivery path.
7. Revoke the old credential after the new credential is confirmed working.

For bundled Postgres password rotation, use:

```bash
./manage.sh rotate-db-password
```

This command is only for the bundled Postgres fallback and refuses to run when `DATABASE_URL` is set.

## Relay URL Rotation

Rotate relay URLs when a route URL is exposed, shared too broadly, or no longer has a clear owner.

1. Identify the affected webhook route.
2. Create or regenerate the replacement relay URL through the application workflow.
3. Update the sending system to use the new URL.
4. Send a test message and confirm the delivery event.
5. Disable or remove the old route URL.
6. Review recent delivery events for unexpected senders or payload patterns.

Avoid publishing relay URLs in tickets, logs, screenshots, documentation, or chat history.

## Rollback

Before applying an update, keep:

- The previous deployable git revision.
- A recent database backup.
- The previous `.env` or equivalent deployment configuration.
- The previous image digest references, if images are managed outside this repository.

Rollback steps:

1. Stop the affected deployment path.
2. Restore the previous git revision or image set.
3. Restore configuration if it changed.
4. Restore the database only if the failed update changed data or migrations made the current database incompatible.
5. Start the stack.
6. Confirm `/api/v1/health`, `/api/v1/readyz`, login, route management, and a test webhook delivery.
7. Record the failed revision and the reason for rollback in the relevant issue or release notes.

For local Docker Compose deployments:

```bash
./manage.sh backup-db
./manage.sh restart
```

Use `./manage.sh restore-db <backup.sql>` only when a database restore is required.

## Recovery Checklist

Use this checklist after a failed deploy, broken update, or suspected configuration drift.

1. Confirm which revision and image digests are running.
2. Capture backend, frontend, proxy, and Postgres logs.
3. Check `/api/v1/health` and `/api/v1/readyz`.
4. Confirm database connectivity and available disk space.
5. Confirm secret values are present and match the expected deployment configuration.
6. Confirm proxy routes `/api/*` to backend and all other paths to frontend.
7. Run a minimal authenticated admin workflow.
8. Send a test webhook through a non-production route or a route approved for testing.
9. Decide whether to roll forward, roll back, or keep the service stopped until the root cause is fixed.

## Exception Handling

Temporary scan or audit exceptions must be narrow and reviewable.

Each exception must include:

- The affected tool or scan.
- The affected package, image, or path where possible.
- The reason it cannot be fixed immediately.
- An expiry date.
- The condition that removes the exception.

Remove exceptions as part of the next successful dependency or image update that makes them unnecessary.

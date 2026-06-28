# Deployment

## Supported Deployment Shapes From This Repository

The repository directly supports:

- Docker Compose stack with Postgres, backend, frontend, and HAProxy.
- Local development with separate backend and frontend processes.

No Kubernetes manifests, Terraform, Helm chart, hosted image registry, or production deployment pipeline is present in the repository.

## Docker Compose Stack

Start:

```bash
cp .env.example .env
docker compose up -d --build
```

Services:

| Service | Purpose | Exposed port |
|---|---|---|
| `proxy` | HAProxy routes `/api/*` to backend and all other paths to frontend. | `${PROXY_HTTP_PORT:-8080}:80`, `${PROXY_HTTPS_PORT:-8443}:443` |
| `frontend` | React/Vite build served by nginx. | Internal `80` |
| `backend` | FastAPI app served by Uvicorn. | Internal `8000` |
| `postgres` | Local Postgres database. | Host `5432` |

HAProxy health checks:

- Backend: `/api/v1/health`
- Frontend: `/`

The Compose stack uses a fixed internal network so the backend can trust `X-Forwarded-For` only when the direct client is the bundled HAProxy container:

- `proxy`: `172.30.0.10`
- `backend`: `TRUST_X_FORWARDED_FOR=true`
- `backend`: `TRUSTED_PROXY_IPS=172.30.0.10`

This lets automatic abuse blocking group attempts by the real caller IP instead of the proxy IP. Do not broaden `TRUSTED_PROXY_IPS` to public networks; clients must not be able to self-declare their source address.

The proxy generates or uses local development certificates in `devcert/` through `haproxy/start-haproxy.sh`. This is suitable for local development only.

## Ports

Default local URLs:

- HTTP UI: `http://localhost:8080`
- HTTPS UI with local cert: `https://localhost:8443`
- API docs through proxy: `http://localhost:8080/api/v1/docs`

If a port is already in use, change `PROXY_HTTP_PORT` or `PROXY_HTTPS_PORT` in `.env`.

## Persistent Data

Docker Compose stores database data in the `postgres_data` volume.

The backend default outside Docker is SQLite at:

```text
sqlite:///./app.db
```

The Docker backend overrides this to the bundled Postgres service.

## Secrets

Use placeholders only in `.env.example`. For production-like deployments, move secrets into the deployment platform's secret mechanism.

Sensitive values include:

- `SESSION_SECRET`, if provided instead of the generated instance secret
- `SETTINGS_ENC_KEY`
- `MS_APP_CLIENT_SECRET`
- `MONITORING_API_KEY`
- Generated relay URLs
- Delegated Graph refresh material stored in the database

When `SESSION_SECRET` is omitted, Teams Rehook stores a generated instance secret in the application database. This is suitable for local and simple shared-database deployments. If `SESSION_SECRET` is provided by a secret manager, every backend replica in that environment must receive the same value.

`SETTINGS_ENC_KEY` is not derived from `SESSION_SECRET`. When it is omitted, startup stores a separate generated settings encryption key in the database for local/simple shared-database deployments. Production-like deployments should provide `SETTINGS_ENC_KEY` through durable secret management. Changing it without re-encrypting or re-entering stored secrets makes existing encrypted settings and delegated refresh material unreadable.

## TLS And Reverse Proxy

The local HAProxy config binds HTTP and HTTPS and forwards:

- `/api` and `/api/*` to backend.
- All other paths to frontend.
- `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host` to the backend.

For production, define TLS termination and public URL policy outside this repository. If another reverse proxy replaces HAProxy, set `TRUSTED_PROXY_IPS` to that proxy's private IP address or CIDR range and keep `TRUST_X_FORWARDED_FOR=true` only when that direct proxy boundary is controlled.

TODO: Document the intended production reverse proxy, TLS certificate source, HSTS policy, and allowed public origins.

## Local Bare Process Development

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `5173` and proxies `/api` to `http://localhost:${PROXY_HTTP_PORT}`, defaulting to `8080`. If the backend runs directly on `8000` without HAProxy, set `PROXY_HTTP_PORT=8000` in `.env` or start the backend on the configured proxy port.

## Health Checks

Use:

```text
GET /api/v1/health
GET /api/v1/readyz
```

`/readyz` executes `SELECT 1` against the configured database.

## Update Strategy

No formal release process is visible in the repository. Until one exists:

1. Back up the database.
2. Review `CHANGELOG.md`.
3. Run validation.
4. Rebuild images.
5. Start the stack.
6. Check health, readiness, and route tests.

```bash
npm run test
docker compose up -d --build
```

## Rollback

TODO: Define rollback procedure for production deployments.

At minimum, keep a database backup and previous deployable revision before applying changes.

## Production Gaps

Before production rollout, define:

- Public hostname and TLS policy.
- Secret storage.
- Database backup and restore.
- Monitoring and alerting.
- Operational ownership and support path.
- Supported versions.
- Incident response and vulnerability reporting workflow.

# Teams Rehook

Teams Rehook is an authenticated internal tool for relaying webhook messages into Microsoft Teams.

It gives operators stable relay URLs, route management, delivery testing, Teams target capture, and delivery logs without requiring every source system to know Microsoft Teams delivery details.

## Who It Is For

Teams Rehook is intended for teams that need to forward operational events from monitoring, firewall, or internal systems into Microsoft Teams. The current implementation is an MVP/evaluation-stage application; production rollout still depends on tenant-specific Microsoft Teams bot setup, Microsoft Graph permissions, operational ownership, and security hardening.

## Key Features

- Stable relay URLs for external webhook sources.
- Authenticated operations UI for route management, testing, settings, logs, and readiness checks.
- Bot Framework delivery to captured Teams conversation references.
- Microsoft Graph target lookup and delegated Graph delivery for supported Graph routes.
- Payload handling for plain text, JSON objects, JSON arrays, and Adaptive Card activities.
- Payload Generator for building example JSON bodies.
- Delivery events, audit logs, retention cleanup, and API-key protected machine monitoring.
- Relay URL regeneration with immediate invalidation of the previous URL.

See the [feature matrix](docs/feature-matrix.md) for the current capability overview.

## Quickstart

Prerequisites:

- Docker and Docker Compose.

Start the local Docker stack:

```bash
./manage.sh start
```

On first run, `./manage.sh start` launches the guided `.env` setup if the file is missing, lets you pick a setup profile, then asks whether the stack should start immediately. The recommended `local` profile publishes HTTPS on `https://localhost:8443` with a self-signed development certificate and enables the secure session cookie.

Open the application:

```text
https://localhost:8443
```

The browser warns about the self-signed development certificate; accept it for local use.

The API documentation is available at:

```text
https://localhost:8443/api/v1/docs
```

On first startup, open the application and complete the first-run setup screen. The setup flow creates the first admin with the email, display name, and password you provide.

After signing in, open `Settings` to add Microsoft Entra values, adjust URLs, and review delivery readiness. The app starts without Microsoft credentials; real Teams delivery becomes available after those settings are configured.

`SESSION_SECRET` is optional. If it is omitted, the backend generates and stores an instance secret during first startup. Backend replicas that share the same database reuse that generated secret; production deployments can still provide one shared value through a secret manager.

`SETTINGS_ENC_KEY` protects encrypted settings and delegated refresh material. If it is omitted, first startup generates a separate database-backed key for local/simple shared-database deployments; production deployments should provide a stable value through a secret manager.

## Minimal Webhook Example

After creating a route in the UI and copying its relay URL, send a JSON payload:

```bash
curl -X POST "YOUR_RELAY_URL" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test alert","message":"Webhook connected successfully","severity":"info"}'
```

Treat relay URLs as secrets. Anyone with a valid relay URL can send messages to the connected Teams target.

## Configuration

`./manage.sh setup` writes a small `.env` through a guided wizard with `local`, `production`, and `custom` profiles, and can start the stack afterward. `./manage.sh start` runs that guided setup automatically when `.env` is missing. The Docker stack uses the bundled Postgres service by default. Set `DATABASE_URL` only when the backend should use an external Postgres database.

`./manage.sh` provides common single-host Compose operations:

```bash
./manage.sh status
./manage.sh doctor
./manage.sh restart
./manage.sh check-env
./manage.sh sync-env
./manage.sh backup-db
./manage.sh restore-db <backup.sql>
./manage.sh update
```

Full configuration reference:

- [Configuration](docs/configuration.md)
- [Deployment](docs/deployment.md)
- [Admin guide](docs/admin-guide.md)

## Documentation

- [Documentation index](docs/index.md)
- [User guide](docs/user-guide.md)
- [Admin guide](docs/admin-guide.md)
- [Developer guide](docs/developer-guide.md)
- [API reference](docs/api.md)
- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Troubleshooting](docs/troubleshooting.md)

## Development

Run all repository checks:

```bash
npm run test
```

Useful individual checks:

```bash
npm run frontend:build
npm run backend:check
npm run backend:test
```

See [Developer guide](docs/developer-guide.md) and [Contributing](CONTRIBUTING.md).

## Security

Do not commit real tokens, client secrets, route URLs, tenant-specific production configuration, customer data, certificates, or private keys.

Report security issues according to [SECURITY.md](SECURITY.md).

## License

TODO: Add license information.

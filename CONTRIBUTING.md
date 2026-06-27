# Contributing

Teams Rehook is an internal MVP/evaluation-stage tool. Keep changes concrete, scoped, and backed by tests or documentation updates.

## Prerequisites

- Python 3.11 or compatible runtime.
- Node.js and npm.
- Docker and Docker Compose for full-stack validation.

## Local Setup

```bash
cp .env.example .env
docker compose up -d --build
```

For separate local processes, see [Developer guide](docs/developer-guide.md).

## Validation Before Pull Requests

Run:

```bash
npm run test
```

Useful individual checks:

```bash
npm run frontend:build
npm run backend:check
npm run backend:test
```

## Coding Style

- Follow the existing FastAPI, SQLAlchemy, React, Vite, and TypeScript patterns.
- Keep authenticated backend writes behind `require_csrf`.
- Include `X-CSRF-Token` in frontend API client calls for authenticated writes.
- Keep API schemas, frontend types, tests, and docs in sync.
- Preserve the neutral CSS-token design language unless a concrete product direction requires otherwise.

## Branching And Commits

No formal branch or commit convention is visible in the repository.

Recommended default:

- Use focused topic branches.
- Keep commits reviewable.
- Use descriptive commit messages.
- Avoid mixing unrelated refactors with behavior changes.

## Pull Request Expectations

Before review:

- Explain the user-visible or operator-visible change.
- Mention configuration, API, data model, or deployment impacts.
- Include tests for changed backend behavior.
- Build the frontend when UI behavior changes.
- Update documentation when features, APIs, environment variables, operational procedures, or security assumptions change.

## Issues

Use issues for reproducible bugs, scoped feature requests, and operational gaps. Include enough context to reproduce or evaluate the request.

Do not post secrets, tokens, relay URLs, customer data, private IPs, tenant-specific production URLs, or security vulnerability details in public issue text.

## Security

Never commit:

- Real tokens or API keys.
- Client secrets.
- Passwords.
- Private keys or certificates.
- Customer data or personal data.
- Production `.env` files.
- Real relay URLs.

Report vulnerabilities according to [SECURITY.md](SECURITY.md).

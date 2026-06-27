# Security Policy

## Reporting A Vulnerability

TODO: Add security contact address.

Do not report suspected vulnerabilities, exposed credentials, customer data, relay URLs, or tenant-specific production details in public issues.

When reporting privately, include:

- A concise description of the issue.
- Affected component or endpoint.
- Reproduction steps if safe to share.
- Impact assessment.
- Any relevant logs with secrets removed.

Do not include real tokens, client secrets, route URLs, customer data, private keys, or production credentials in reports unless the agreed private reporting channel explicitly supports secure handling.

## Supported Versions

TODO: Define supported versions and security update policy.

The repository currently identifies the application as version `0.1.0` in configuration/package metadata.

## Secrets And Sensitive Data

Never commit:

- `.env` files with real values.
- `SESSION_SECRET`
- `SETTINGS_ENC_KEY`
- `MS_APP_CLIENT_SECRET`
- `MONITORING_API_KEY`
- Bootstrap admin passwords.
- OAuth tokens or delegated Graph refresh material.
- Real relay URLs.
- Private keys, certificates, or customer data.

Use placeholders in examples and documentation.

## Operational Security Notes

- Treat relay URLs as secrets.
- Rotate relay URLs if they may have been exposed.
- Use HTTPS and `SESSION_SECURE_COOKIE=true` for production-like environments.
- Restrict access to the admin UI and monitoring endpoint.
- Grant Microsoft Graph permissions deliberately and with tenant admin review.
- Confirm readiness, monitoring, and logs do not expose secret material before sharing output.

## Response Expectations

No fixed SLA is currently defined. Maintainers should acknowledge valid reports through the configured private security contact once that contact is added.

TODO: Define triage ownership, expected response windows, severity levels, and disclosure process.

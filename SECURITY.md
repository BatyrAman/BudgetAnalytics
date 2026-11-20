# Security Policy

## Supported versions

BudgetAnalytics has no tagged releases yet. Security fixes are made on the `main` branch only.

| Version | Supported |
|---|---|
| `main` (0.1.x, pre-release) | Yes |
| Anything else | No |

## Reporting a vulnerability

**Please do not report vulnerabilities in public GitHub issues, discussions or pull requests**, and do not share exploit details publicly before a fix is released.

Report privately through: **[OWNER: confirm the channel, for example GitHub private vulnerability reporting (repository → Security → Report a vulnerability) once it is enabled, or a dedicated security e-mail address]**.

> Until the owner confirms a channel, there is no verified private reporting route. Do not disclose details publicly in the meantime.

Please include:

- the affected component (frontend, API, Docker setup) and the commit or version;
- steps to reproduce, and the impact you observed;
- whether real user data could be exposed;
- your contact details, if you want to be credited or contacted.

Do not include real personal or financial data in a report. Use test accounts.

## What happens next

**[OWNER: confirm or change the target times]**

| Step | Target |
|---|---|
| Acknowledge the report | within 5 working days |
| Initial assessment and severity | within 10 working days |
| Fix or mitigation for critical and high issues | as soon as practical; progress updates at least every 14 days |
| Coordinated public disclosure | after a fix is available, agreed with the reporter |

## Testing rules

- Test only against **your own local instance** (`docker compose up`; see the [README](README.md#7-quick-start-with-docker)).
- Do not test any hosted instance without the operator's written permission.
- No denial-of-service, social engineering, spam, or access to other people's data.

## Security measures

The implemented controls are summarized in the [README](README.md#12-security) and reviewed in [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) and [docs/implementation/QA_REPORT.md](docs/implementation/QA_REPORT.md). Known open items (for example, no account deletion yet and no encryption at rest provided by the app) are listed there.

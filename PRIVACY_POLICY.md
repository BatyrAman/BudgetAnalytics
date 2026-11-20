# Privacy Policy — DRAFT

> **Draft for owner and legal review. Not in effect.** It describes what the BudgetAnalytics software does with personal data, as verified in the source code (2026-11-20). Items in **[OWNER: …]** must be completed by the operator, and the whole text must be reviewed by a qualified lawyer, in particular for Kazakhstan requirements (see [docs/legal/DATA_PROTECTION.md §7](docs/legal/DATA_PROTECTION.md#7-questions-for-legal-review-kazakhstan-and-international)). This draft does not claim compliance with any law.

**Who this applies to.** BudgetAnalytics is currently self-hosted software: whoever runs an instance is responsible for the personal data in it. This draft is written for a future hosted service run by **[OWNER: legal name of the operator, country, registration details]**. Contact for privacy questions: **[OWNER: e-mail or postal address]**.

## 1. What we collect

| Data | Why |
|---|---|
| Your name and e-mail address | To create your account, sign you in and address you in the app |
| Your password, stored only as a one-way Argon2 hash | To verify your login |
| Session records (refresh-token ids and their expiry or revocation) and two session cookies | To keep you signed in safely and to let you sign out on all devices |
| Financial data you enter or import: accounts (name, type, currency, bank, **only the last 4 digits** of a card, opening balance), transactions (amount, date, type, category, description, merchant), budgets, goals, deposits, custom categories | To provide the budgeting, analytics, goal and deposit features |
| Statement import records: file name, size, a checksum of the file, the period, row counts and, until you confirm or the preview expires, the parsed rows | To let you review rows before saving them and to avoid duplicates. **The uploaded file itself is not kept.** Card-like numbers in descriptions are masked. |
| AI feature usage records: feature, provider, model, token counts, cost, duration | To enforce usage limits and control costs. **Your questions and the answers are not stored.** |
| Your IP address, held briefly in memory (at most one hour) for rate limiting, and a scrambled (hashed) form of your e-mail for login limits | To protect accounts against password guessing and abuse |
| Technical logs: request method, path, status, duration, request id | To operate and troubleshoot the service. Logs do not contain your IP address or the content of your requests. |

We do **not** ask for your IIN, full card or account numbers, bank passwords, location or contacts. The app does not use analytics, tracking or advertising cookies.

**Stored in your browser:** two essential session cookies (`httpOnly`, so scripts cannot read them), your theme and your time zone setting.

## 2. Why and on what basis

We use your data only to provide the features you use, to keep the service secure and to meet legal obligations. The legal basis (consent, contract or another ground under applicable law) is **[OWNER / LEGAL: to be confirmed for Kazakhstan law; see DATA_PROTECTION.md Q-3]**.

We do not sell your data and do not use it for advertising.

## 3. AI advisor (optional)

The advisor works in one of two modes:

- **Rule-based** (the default): no data leaves our servers.
- **AI provider** (only if the operator enables it): your question and a summary of your figures are sent to an external AI provider.

What the provider receives in the AI mode:

- calculated totals and rates;
- your own category, budget and goal names, **replaced by neutral labels**;
- your question, with e-mail addresses, card numbers, 12-digit numbers and phone numbers removed.

It does **not** receive your name, e-mail, account names or numbers, or transaction descriptions. Please do not type other personal details into questions, because they are not removed automatically.

Provider used: **[OWNER: name, country/region, link to its data-processing terms, whether data may be retained or used for training]**. Using the provider may involve transferring data outside Kazakhstan: **[LEGAL: conditions and consent, see DATA_PROTECTION.md Q-2]**.

## 4. Who else receives data

No one, except:

- **hosting and infrastructure providers** that store or process data for us: **[OWNER: list, with countries]**;
- the **AI provider**, if enabled (section 3);
- authorities, where the law requires it.

## 5. Where data is stored

**[OWNER: country and provider of the database, backups and logs]**. **[LEGAL: data localization requirements, see DATA_PROTECTION.md Q-1]**.

## 6. How long we keep it

- **Account and financial data:** until you delete it or your account is deleted. **[OWNER: retention period after account closure.]**
- **Import previews that you do not confirm:** their rows are deleted after 24 hours, the next time you use the import feature.
- **Rate-limit data:** at most 1 hour, in memory.
- **Session cookies:** the access cookie lasts about 30 minutes, the refresh cookie up to 7 days, unless you sign out earlier.
- **Logs and backups:** **[OWNER: retention periods]**.

## 7. Your choices and rights

**What you can do in the app today:**

- view and correct your data;
- delete individual transactions, budgets, goals, deposits, custom categories and imports;
- archive financial accounts;
- change your password;
- sign out on all devices.

**Not yet available in the app:** deleting your whole account and exporting your data. Until these are built, send requests to **[OWNER: contact]**, and the operator will handle them manually within **[OWNER/LEGAL: deadline]**.

Other rights under applicable law (for example, withdrawing consent): **[LEGAL: list and procedure]**.

## 8. Security

- Passwords are hashed.
- Sessions use short-lived tokens in secure cookies; refresh tokens rotate, and reuse is detected.
- Every request is limited to your own data.
- Requests are rate-limited, and browser security headers are set.

No system is perfectly secure. If you notice a problem, contact **[OWNER: contact]**; security researchers should see [SECURITY.md](SECURITY.md).

## 9. Children

The service is not intended for children. Minimum age: **[OWNER/LEGAL: age]**.

## 10. Changes

We will announce material changes to this policy **[OWNER: how, for example by e-mail or in the app]** before they take effect.

*Version: draft, 2026-11-20. Effective date: [OWNER].*

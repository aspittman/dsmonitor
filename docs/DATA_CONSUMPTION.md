# Data consumption audit — 2026-10-10

Owner reports Supabase log ingestion at 703% quota, egress at 302%, and 2,584 API gateway requests. Reporting period, absolute limits, and Vercel billing totals remain unknown.

## Confirmed findings and mitigation

* Idle approved workers fetched every row from nine feedback tables, and downloaded context again after claiming work. Eight worker invocations were scheduled every fifteen minutes. That schedule is paused.
* Integrated capabilities ran every 45 seconds, alongside a separate two-minute cron. The redundant cron is paused; integrated checks now run every five minutes with a shared minimum-cycle timestamp.
* CRM history cache now lasts fifteen minutes; connectivity cache lasts five minutes. Failed reads are cached too.
* PostgreSQL audit found statement logging set to `ddl`, pgAudit disabled, connection/duration logging disabled. Full SQL statement logging does not explain the reported log ingestion. Exact source attribution still requires provider logs/usage access.
* The restarted dashboard's CRM check returned HTTP 402. Shared backoff suppressed 38 follow-up requests during its first collection. Supabase organization access also failed; an error alone does not establish its billing cause.

## Meter coverage

The Data usage tab reads a local SQLite hourly aggregate, ranks engines and processes by sent/received HTTP body bytes, and lists destinations, requests, errors and deferred calls. Credentials, payloads, query strings and arbitrary URL paths are excluded. It makes no cloud requests itself.

Metering covers DSMonitor and configured Python subprocess launchers, plus two existing MMonolith cron entry points. Nested launchers that strip PYTHONPATH, remote workers, browser traffic, PostgreSQL wire traffic and CRM-to-Supabase queries are outside coverage. Streaming/error bodies and TLS/header overhead are excluded. Measurements start October 10; historical per-engine usage cannot be reconstructed from this meter. Log ingestion is a separate provider metric. Owner-reported totals are explicitly labeled snapshots, not live billing data.

## CRM rollout pending

Local CRM commit `6c4d239` adds authenticated `GET /api/bot/feedback-loop/work-context`, scoped to organization, service, action and RUNNING status. It returns at most one execution request, one linked report and 100 linked evidence rows. Domain review and client brief workers now use this endpoint; feedback learning is skipped without a newly recorded review result. Existing execution approval and zero-spend checks remain in force.

Publishing failed: terminal Git authentication points to an unavailable VS Code credential socket; the GitHub connector returned 403 on file writes. Workers remain paused until this endpoint is deployed and checked. Do not resume the schedule against the old CRM endpoint.

Provider account restrictions and consumed quota have not been reset. Supabase/Vercel plugin connections were suggested but are not connected. Provider access is needed to investigate log-ingestion contributors and verify Vercel totals.

## Validation

155 DSMonitor tests passed; eight domain review worker tests passed; six CRM test files passed; CRM TypeScript check passed. Separate bounded-endpoint checks verified authorization, invalid-service rejection, idle one-query behavior, organization filters, exact request selection and row limits. Chromium verified the live Data usage tab, filters, mobile width and absence of JavaScript errors.

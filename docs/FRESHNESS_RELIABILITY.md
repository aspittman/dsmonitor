# Live readiness and freshness validation — 2026-09-29

Dsmonitor now runs bounded read-only capability probes automatically alongside the
web application, on a 45-second start-to-start schedule. All five configured
publishers were observed renewing their timestamps without a business run or a
manual diagnostic. Existing cron invocations share the exclusive probe lock.

Current readiness is separate from historical writes, run outcomes and observed
workflow progress. Engine cards explicitly identify the services covered by their
checks. Disabled services remain NOT_CONFIGURED; unregistered historical fragments
do not redefine the engine's capability contract. READY verifies connectivity,
required reads and the endpoint's service/adapter configuration checks, not a
successful business execution or permission to purchase/send.

Capability verification expires after 90 seconds. Collection itself expires after
45 seconds. API reads re-evaluate expiry even if the collector stops. `/healthz`
returns 503 when collection is absent/stale. The browser uses the served timestamp
and monotonic elapsed time to expire current badges independently of further
responses. Fetches time out after eight seconds. History retains source timestamps.
Infrastructure cache expiry includes scheduling headroom to avoid false stale
flashes between scheduled refreshes.

## CRM deployment

Commit `a739f6c` was pushed from an isolated clean checkout to the CRM deployment
branch. Only two authenticated GET routes and their tests were deployed:

- `/api/bot/monitoring-capabilities`: fixed table contracts, scoped SELECT LIMIT 1,
  service enablement and execution-adapter registration checks.
- `/api/bot/monitoring-context`: fixed lightweight columns, latest 100 records per
  table, explicit failed-table/coverage reporting. Research candidate arrays,
  execution payloads and decision snapshots are excluded.

Live responses were about 567 bytes for the DevSpace One readiness request and
19,641 bytes for the tenant history request, with no failed tables. The previous
unbounded-context fallback is removed from the capability publisher. No migrations,
role grants, purchases, approvals or outreach were performed. Unrelated local CRM
changes were excluded; synchronized monitoring-file originals were backed up in
`/tmp/dsmonitor-crm-monitoring-backup`.

## Validation and remaining observed issues

- 139 Python tests passed, including scope validation, missing credentials/routes,
  permission rejection, stale publishers, stopped collection, repeated scheduling,
  disabled service handling and historical-outcome independence.
- CRM monitoring route tests and deployment TypeScript checks passed.
- Browser test passed against the running dashboard: current labels, check times,
  next actions and visible STALE transitions after simulated lost updates; no
  browser errors. The simulation was browser-local and wrote no source records.
- Automatic renewal evidence is in `data/freshness-validation.json`. It is a dated
  validation observation, not a replacement for live `/api/status`.
- Domain Merchant readiness checks verified Mmonolith, Decision Engine and CRM;
  DevSpace One remains BLOCKED because its domain-review adapter is not registered
  ready. Monitoring does not enable an unverified adapter to clear a badge.
- The independent Supabase monitoring role receives permission error 42501 when
  reading organizations. The dashboard labels this as a monitoring-access gap,
  distinct from verified engine access through CRM. No privileges were widened.
- Missing market/buyer/quote evidence remains a business workflow issue. Frequent
  readiness checks do not rerun business evaluation or manufacture evidence.

The dashboard process was restarted with these changes. New app starts automatically
start the capability scheduler; there is no extra watch command required.

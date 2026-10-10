# Data consumption audit — 2026-10-10

Owner reports Supabase log ingestion at 703% quota, egress at 302%, and 2,584 API gateway requests. The reported billing cycle is September 23–October 23, with an egress grace deadline of October 11. Absolute limits and Vercel billing totals remain unknown.

## Confirmed findings and mitigation

* Idle approved workers fetched every row from nine feedback tables, and downloaded context again after claiming work. Eight worker invocations were scheduled every fifteen minutes. That schedule is paused.
* Integrated capabilities ran every 45 seconds, alongside a separate two-minute cron. The redundant cron is paused; integrated checks now run every thirty minutes with a shared minimum-cycle timestamp. Capability observations expire after 90 minutes, allowing missed checks without immediately marking healthy engines stale. This halves scheduled probe frequency compared with the previous fifteen-minute setting; it does not limit CRM business requests.
* CRM history cache now lasts fifteen minutes; connectivity cache lasts five minutes. Failed reads are cached too.
* PostgreSQL audit found statement logging set to `ddl`, pgAudit disabled, connection/duration logging disabled. Full SQL statement logging does not explain the reported log ingestion. The provider log audit below identifies API gateway traffic as the dominant retained source.
* The restarted dashboard's CRM check returned HTTP 402. Shared backoff suppressed 38 follow-up requests during its first collection. Supabase organization access also failed; an error alone does not establish its billing cause.

## Meter coverage

The Data usage tab reads a local SQLite hourly aggregate, ranks engines and processes by sent/received HTTP body bytes, and lists destinations, requests, errors and deferred calls. Credentials, payloads, query strings and arbitrary URL paths are excluded. It makes no cloud requests itself.

Metering covers DSMonitor and configured Python subprocess launchers, plus two existing MMonolith cron entry points. Nested launchers that strip PYTHONPATH, remote workers, browser traffic, PostgreSQL wire traffic and CRM-to-Supabase queries are outside coverage. Streaming/error bodies and TLS/header overhead are excluded. Measurements start October 10; historical per-engine usage cannot be reconstructed from this meter. Log ingestion is a separate provider metric. Owner-reported totals are explicitly labeled snapshots, not live billing data.

## CRM rollout pending

Local CRM commit `6c4d239` adds authenticated `GET /api/bot/feedback-loop/work-context`, scoped to organization, service, action and RUNNING status. It returns at most one execution request, one linked report and 100 linked evidence rows. Domain review and client brief workers now use this endpoint; feedback learning is skipped without a newly recorded review result. Existing execution approval and zero-spend checks remain in force.

Publishing initially failed. After the GitHub app installation was corrected, the bounded endpoint was published as commit `0fbac7ae549cef25baaae5aa85c4e8432ee90b7f`. No deployment status has yet been reported for that commit. Workers remain paused until the production endpoint is verified. Do not resume the schedule against the old CRM endpoint.

Provider account restrictions and consumed quota have not been reset. Supabase log access is now verified through the authenticated Management API using the existing CLI credential. Vercel billing totals remain unverified.

## Provider log and backup audit

Read-only Management API checks on October 10 found the following retained log totals for October 9 19:18:41 UTC through October 10 19:18:41 UTC:

| Source | Entries | Estimated entry bytes |
| --- | ---: | ---: |
| API gateway (`edge_logs`) | 54,478 | 134,882,298 |
| PgBouncer | 11,609 | 3,242,360 |
| PostgreSQL | 1,478 | 1,812,002 |
| PostgREST | 3,674 | 949,792 |
| Supavisor | 67 | 58,364 |
| Storage | 11 | 10,938 |
| Realtime | 7 | 5,294 |

Bytes are message length plus serialized log attributes, not provider billing measurements. API gateway entries account for approximately 96% of this estimate. A nearby 24-hour path breakdown found 19,061 successful GETs to `organization_services`, 19,062 to `intelligence_reports`, and 14,826 to `execution_results`, plus 1,458 unauthorized GETs to `organizations`. These resource names omit query strings and record identifiers.

The three dominant resources match `scripts/client_direct_probe.py`, invoked by capability checks for direct research services. This supports excessive diagnostic polling as the leading process attribution, but the retained gateway logs lack a distinguishing client tag, so individual requests cannot be conclusively assigned to that process. The redundant two-minute cron and previous 45-second integrated capability cadence multiplied these probes. The later one-hour window (October 10 18:17:47–19:17:47 UTC) contained only seven gateway entries, consistent with reduced current traffic; it does not prove the entire historical billing-cycle cause.

Supabase's current Logs Ingest documentation marks the metric as not yet billed with a grace period through the start of 2027. The owner's egress warning remains a separate restriction risk. See https://supabase.com/docs/guides/platform/manage-your-usage/logs-ingest.

The authenticated backup listing returned no listed backups (`backups: null`) and `pitr_enabled: false`. An enabled internal WAL-G flag does not establish an accessible restore point. No independent scheduled export has been verified. Free-plan projects should maintain their own off-site database exports; storage object contents require separate backup. See https://supabase.com/docs/guides/platform/backups.

The CLI schema export attempt failed because Docker was unavailable; no completed backup was created. `scripts/backup_supabase.sh` prepares private roles/schema/data exports using an already linked CLI project, checks command success and nonempty files, and writes checksums plus a completion marker. It requires Docker and does not upload or schedule backups. Store an encrypted copy off-site and validate restoration separately. Exports themselves consume egress; start with one export and choose a weekly schedule while usage is low rather than frequent full dumps.

## Validation

155 DSMonitor tests passed; eight domain review worker tests passed; six CRM test files passed; CRM TypeScript check passed. Separate bounded-endpoint checks verified authorization, invalid-service rejection, idle one-query behavior, organization filters, exact request selection and row limits. Chromium verified the live Data usage tab, filters, mobile width and absence of JavaScript errors.

## Direct Supabase connection and process warnings

DSMonitor now uses a dedicated `dsmonitor_usage_reader` login over TLS through the Supabase session pooler. The password stays in the ignored, mode-600 `.env`. The role defaults to read-only transactions, has no organization INSERT privilege, and uses the aggregate-only `public.dsmonitor_overview()` function. Anonymous/authenticated/public execution privileges on that function are revoked. See `sql/supabase_monitoring.sql` for its non-secret definition.

The database check reads database size, active/total connection counts, and aggregate workflow/execution status counts. These are refreshed every five minutes independently of Vercel; the Data usage endpoint serves the cached result. Storage size is not bandwidth. The live check succeeded.

Largest decoded response bytes are now retained per process/endpoint. Daily warning thresholds default to 20 MiB transferred per process, 1,000 requests per process, or a 1 MiB response. They apply to today's non-local measured traffic in UTC and do not stop business jobs. Override positive integer thresholds with `data/usage-thresholds.json`:

```json
{"daily_process_bytes":20971520,"daily_process_requests":1000,"large_response_bytes":1048576}
```

These defaults are monitoring heuristics, not the user's provider plan limits. The local meter cannot enforce a provider-wide quota for traffic outside its coverage.

Two research launchers now preserve instrumentation into Decision Engine/DevSpace One subprocesses. Orchestrator child processes identify their own engine and service/stage, and the research cron labels distinguish client-cycle from service-demand. Detailed local process measurements start with each instrumented run.

Updated validation: 159 DSMonitor tests passed, including migration of the existing consumption database, process warnings, and direct-connection adapter behavior. Chromium verified the live tab, filters, and mobile layout. The live database summary and read-only login were checked independently. 38 orchestrator control-plane/service/product adapter tests also passed with production database configuration disabled for the local test run.

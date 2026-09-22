# dsmonitor

A local, read-only monitoring dashboard for the DevSpace ecosystem. It observes engine availability, dependency probes, existing workflow records, ID-linked CRM evidence, log errors and monitoring history. DevSpace does not import, call, or depend on dsmonitor.

## Start

The virtual environment is installed in this folder:

```bash
cd /home/aaron/MyBotz/dsmonitor
./venv/bin/python app.py
```

Open **http://127.0.0.1:5055**. Stop with Ctrl+C. The process binds only to loopback; non-loopback clients and unexpected Host headers are rejected. No login or public deployment is provided: this is an owner/admin tool on a trusted local machine.

For a fresh installation (Python 3.10+):

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
```

`requirements.lock.txt` records the exact environment used for validation, including development tools. Runtime dependencies are Flask and psycopg; SQLite is part of Python. Browser code uses plain JavaScript and CSS, with no external CDN or build step.

## Current source coverage

| System | Monitoring source | What it establishes |
|---|---|---|
| MMonolith | Local Python process, `logs/*.log`, `data/demand_seeker.sqlite3`, linked workflow/CRM records | Availability evidence, stored reports, real UTC observation/report counts, recorded workflow activity |
| Decision Engine | Local Python process; configured captured JSON stdout; orchestrator stages and CRM recommendations | Availability and attributable recommendation activity; no built-in HTTP heartbeat was found |
| DevSpace One | Local Python process, existing service logs, orchestrator execution stages and CRM results | Availability, recorded failures, explicit request/result references |
| dsorchestrator | Local Python process; existing SQLite or configured PostgreSQL `workflow_runs` / `stage_runs` | Actual workflow status, stage owner, attempts, timestamps and references |
| CRM | Authenticated GET to `/api/decision-engine/organizations`; optional organization-scoped context GETs | CRM API accessibility, explicitly scoped business labels and source records |
| Supabase | Independent PostgREST GET on `organizations`, or read-only PostgreSQL `SELECT 1` | Database/API connectivity and access under the configured credential; not every engine's database permissions |

**Current diagnosis:** the configured deployed CRM monitoring route returns HTTP 404. Supabase Auth health returns 200 and the database answers with PostgreSQL code 42501: the anonymous monitoring role cannot read `organizations`. Supabase is ONLINE with limited monitoring access; the CRM read gap leaves engine health UNKNOWN, rather than falsely degrading every engine. The local orchestrator database contained zero runs. DevSpace One has real undated traceback errors. These are shown as errors with time unknown; they are not silently discarded. No complete live production workflow was available to validate.

BotMonitor was not found in the inspected local directories. No BotMonitor code or visual identity was claimed as reused. The interface implements the requested dark monitoring style, summary cards, status indicators, automatic refresh, detail views and history. A direct BotMonitor comparison still requires its source location.

## Configuration

Defaults work without a `.env`. To override them, copy `.env.example` to `.env` and edit it. Environment variables take precedence. Never commit `.env`.

- Projects default to sibling directories under `../`. Override with `DSMONITOR_PROJECTS`.
- The existing CRM URL/token are read **server-side only** from `../devspace-one/.env`, with CRM token fallback from `../devspace-crm/.env.local`. Supabase URL and **anon key**, not the service-role key, are discovered from CRM's `.env.local`. Explicit empty overrides disable a probe.
- `DSMONITOR_ORGANIZATION_IDS=["organization-uuid"]` is required for remote workflow state and CRM business context. An empty list reads only the local owner-owned workflow database and CRM connectivity probe. It does not download every customer's context.
- `DSMONITOR_ORCHESTRATOR_SQLITE` defaults to `../dsorchestrator/data/orchestrator.sqlite3`. A `DSMONITOR_ORCHESTRATOR_DSN` selects shared PostgreSQL instead; there is no silent fallback to a different backend if that database fails.
- `DSMONITOR_SUPABASE_DSN` optionally selects an independent read-only PostgreSQL probe instead of PostgREST. Use a database role limited to SELECT. The monitor additionally requests read-only sessions and a statement timeout.
- `DSMONITOR_HEALTH_URLS` maps engine IDs to existing read-only health endpoints. No endpoints were added to other projects. A successful JSON health response must contain `status: "OK"` or `"HEALTHY"` to establish engine health.
- `DSMONITOR_HEARTBEAT_FILES` optionally maps engine IDs to JSON files containing a source-generated ISO `timestamp`. Monitor never creates source heartbeat files. Freshness defaults to 120 seconds.
- `DSMONITOR_LOG_FILES` maps engine IDs to additional captured stdout/log paths. JSON lines and existing dated text logs are supported. At most 10 files, 64 KiB and 100 trailing lines per file are examined per poll.
- `DSMONITOR_LOG_TIMEZONE` supplies an IANA timezone **only if known** for naive source log timestamps. Without it, such timestamps remain time unknown. An observation timestamp is not an execution timestamp.
- Browser/health refresh: `DSMONITOR_REFRESH_SECONDS=10`. Expensive CRM contexts are cached for `DSMONITOR_CRM_CONTEXT_SECONDS=120`, with observation time displayed. Requests have a three-second timeout by default. A collection cycle takes its read duration plus the refresh delay; refresh does not start overlapping collections or multiply polling for each browser.
- Snapshots: `DSMONITOR_SNAPSHOT_SECONDS=120`. Retention: `DSMONITOR_RETENTION_DAYS=30`. Workflow window: `DSMONITOR_LIMIT=200`. When the window is incomplete, summary process totals become N/A rather than misleading partial totals.
- `DSMONITOR_STALE_SECONDS={"domain":{"execution":600}}` enables a per-process, per-stage threshold. The default is `{}`: no unsupported runtime assumptions. The basis is the workflow's last state update, not proof the engine has stopped.

Use dsmonitor's `.env` for monitoring settings; do not change operational code or run a workflow just to fill the dashboard.

## Reading the dashboard

**Overview:** four engine cards and two infrastructure cards, with separate availability and overall health. Click a card for the exact checks, dependencies, heartbeat, successful activity, metrics, errors and attributed workflow activity.

**Processes:** domain, scholarship, DevSpace services/outreach and CRM businesses are registered initially. Filters cover type, business/organization, engine, status and current stage. Actual run rows come from source state. A category without records shows NO DATA; Schopath shows NOT CONFIGURED until there is an attributable workflow. CRM recommendations outside orchestrator tracking appear as explicitly labelled recommendation lifecycles, not fabricated complete runs.

**Details:** stages and attempts come from source rows. The known seven-stage domain order is research → decision → approval → execution → feedback → updated intelligence → redecision, matching the inspected orchestrator declaration. Other stage names are retained. No measurement/dispatch stage is invented. Durations require both source timestamps. Missing references remain UNVERIFIED. Completion asserted by the orchestrator is distinguished from independent CRM record verification.

**Errors and activity:** real records, with engine, source/run, tenant and retry information when known. Log messages are sanitized; arbitrary successful stdout is reduced to a generic log observation so customer payloads are not copied. Identical log entries are grouped with their count in the scanned tail so repeated tracebacks do not hide other services. Undated errors stay visible without establishing a current failure rate. UTC daily totals never count them as “errors today.”

**History:** local snapshots and deduplicated observed events, starting when dsmonitor collects them. Click a snapshot for engine and process state at that observation. Older source events may be observed today, but no earlier monitor snapshots are fabricated. A brief event between polls can be missed if the source itself does not retain it.

## Health semantics

| Status | Evidence / meaning |
|---|---|
| ONLINE | Process, heartbeat, API or database response observed; full health/access not established |
| HEALTHY | Explicit healthy engine API and healthy configured dependencies, or successful scoped infrastructure probe |
| DEGRADED | Dependency failure, recent dated failures, or responding API without a healthy result |
| STALE | Configured heartbeat or workflow inactivity threshold exceeded |
| ERROR | Server-side failure or explicit source failure; individual monitoring-access checks can also be red without implying engine failure |
| OFFLINE | Configured endpoint could not be reached; this is an observed probe result, not proof the entire service is down |
| UNKNOWN | Missing configuration, unavailable monitoring route/credential, insufficient evidence, unavailable local process visibility or adapter failure |

Batch engines with no current Python process are UNKNOWN, not OFFLINE. Stored successful work never by itself establishes current health. CRM and Supabase are independent probes. A shared database/auth failure is shown on the dependency and explained on affected engine cards. Engine availability remains visible separately. A missing CRM read route (404) or monitor-only authorization error does not prove an engine dependency failed; these are labeled monitoring gaps. A PostgreSQL permission error proves the database answered, while data access remains unverified.

## Read-only and security boundaries

All outbound HTTP requests use GET, reject redirects, and require HTTPS except loopback. Source SQLite connections use `mode=ro` and `PRAGMA query_only=ON`; PostgreSQL sessions request `default_transaction_read_only=on`. No operational CLI or source project module is invoked. No migrations or operational tables are created.

The only runtime writes are dsmonitor's own `data/dsmonitor.db` (monitoring snapshots/events and its SQLite housekeeping). This database is mode 0600 and configurable only within dsmonitor's data directory through normal settings. Raw CRM payloads, approval identities, environment variables and credentials are not returned or stored. Exact known credentials, token/key formats, credential assignments, URLs and emails are redacted before rendering and persistence. The UI escapes source text and applies a restrictive Content Security Policy.

There are no approve/reject/start/stop/retry/purchase/send/configuration APIs. Dashboard APIs are GET-only and contain no operational transport of their own. Adapter, CRM, Supabase and local history failures are isolated; the last collection timestamp makes stale monitor output explicit.

## Verification and extension

```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest -q
./venv/bin/python scripts/verify_sources.py
# Inspect an EXISTING workflow; never starts or advances it:
./venv/bin/python scripts/verify_sources.py --workflow EXISTING_RUN_UUID
# With dsmonitor running and Chromium installed:
./venv/bin/python scripts/browser_check.py
```

The tests use temporary source fixtures and injected outages; they never approve recommendations or send operational requests. The browser check captures the real dashboard under `docs/`.

Register a category without changing the dashboard:

```python
from process_registry import register_process
register_process(id="google_play", display_name="Google Play", aliases=["google-play"])
```

Or configure `DSMONITOR_EXTRA_PROCESSES` in `.env.example`. New `workflow_type` values and their actual stage rows already render generically. For a new data format, add an adapter returning normalized engine/process/activity fields and wire its read-only collector into `services/monitor.py`. Registering a category alone does not invent an integration or count existing unlinked research as a workflow.

See [the discovery record](docs/DISCOVERY.md), [the 21-point implementation report](docs/IMPLEMENTATION_REPORT.md), and [the manual verification guide](docs/VERIFICATION.md).


## Local scheduling diagnosis

On 2026-09-18, local cron was active. The current user's crontab contained daily DevSpace One jobs for Domain Merchant (08:00), Afternic sync (09:00) and DevSpace Outreach (10:00), using the machine's America/Denver timezone. No matching cron/systemd schedules for MMonolith, Decision Engine or dsorchestrator were found in the inspected local configuration. No job or schedule was changed or executed.

On 2026-09-19, the local crontab was updated for the domain workflow: MMonolith research and feedback at 07:00, Decision Engine at 08:00, and DevSpace One Afternic sync, Apollo drafts, and reviewed Apollo delivery at 09:00 (machine timezone America/Denver). The previous Domain Merchant and Afternic entries were replaced; the unrelated DevSpace Outreach 10:00 entry remains. [The runner](scripts/domain_daily.py) reads the existing DevSpace One `.env`, writes logs under `logs/domain_*.log`, and uses [configured research topics and sender](scripts/domain_daily.json). Missing demand, buyer, registrar, budget, or risk evidence blocks consider-buy recommendations. Apollo drafts require explicit purchased/listed CRM ownership. The CRM owner approves a draft, then DevSpace One sends it as a one-off Apollo email from `aaron@devspacetechnologies.com` and records completed delivery back in CRM. The sender's outbox prevents an ambiguous API response from causing duplicate sends. MMonolith attaches organization-scoped CRM outreach/sale outcomes to the next research report as internal evidence; Decision Engine passes on a domain with sufficient adverse responses. CRM migrations 013–017 and the API routes were deployed on 2026-09-20, and the live research/decision/outreach stages were exercised. Current research has missing demand, buyer, and registrar evidence and no domains are recorded as owned, so all current candidates pass and no Apollo email has been sent.

These observations do not prove the scheduled runs succeeded. Schedule-aware job health still needs actual last-attempt/outcome evidence and configured expectations; the presence of a cron line alone never turns an engine green. See [the current diagnosis and next steps](docs/CURRENT_DIAGNOSIS.md).

## Trace Explorer upgrade

The existing dashboard now includes Workflow Trace Explorer, Engine Trace Explorers,
service views, a clickable Service × Engine matrix, cut-off diagnostics, explicit
retry attempts and opt-in stall detection. Existing process/error/activity/history
views remain available. Start with `venv/bin/python app.py` and open
`http://127.0.0.1:5055`.

Read [the trace upgrade report](docs/TRACE_UPGRADE_REPORT.md) before interpreting
coverage: existing production records do not yet establish a complete correlated
cross-engine workflow. Legacy fragments are labeled, not fabricated into runs.
The report documents actual paths, configuration, schema, validation and remaining
instrumentation work.

Configure `DSMONITOR_TRACE_REGISTRY`, `DSMONITOR_TRACE_THRESHOLDS`, and optional
`DSMONITOR_TRACE_FILES` using JSON environment values (examples in `.env.example`).
A threshold example is:

```json
{"domain_merchant":{"devspace_one":{"execution":{"expected_seconds":600,"stalled_seconds":1200}}}}
```

Thresholds default to disabled. Approval waiting is never automatically stalled.
The optional `services/trace_emitter.py` preserves a caller-supplied context and
returns false on monitoring failures. It is not automatically installed into engines.
Structured producers must reuse the same workflow ID, emit explicit workflow
start/completion events, preserve attempts and propagate parent context when present.
Do not pass credentials or arbitrary business payloads into monitoring events.

Run regression checks with `venv/bin/python -m pytest -q`. The optional
`scripts/browser_trace_check.py` expects an isolated dsmonitor instance on port 5056;
its sample events are browser-only fixtures.

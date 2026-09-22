# Local discovery

Inspected 2026-09-17 through 2026-09-18 before and during implementation. Existing projects were read only. No business module was imported or executed.

## BotMonitor

No BotMonitor directory was found in the inspected `/home/aaron`, `/opt`, or `/mnt` locations. `/home/aaron/MyBotz/cashflow_monitor` is a different application and was not substituted as BotMonitor. A request for BotMonitor's actual path remains unanswered. Stack, components, refresh behavior, licensing and a direct visual comparison therefore cannot be verified. The dsmonitor UI is original, guided by the requested dark monitoring style.

## Located systems

All paths below are relative to `/home/aaron/MyBotz`.

| Project | Runtime and existing observation surfaces | Ownership |
|---|---|---|
| `mmonolith` | Python CLI `main.py`; scheduled research modes; domain intelligence CLI; `logs/demand_seeker.log`; `storage/database.py`; local `data/demand_seeker.sqlite3`; domain intelligence outbox support | Research, observations, reports, predictions, feedback |
| `decision_engine` | Python `main.py` / `decision_engine.main`; JSON logging to stdout in `decision_engine/config/logging.py`; CRM-backed repository | Scoring and recommendations |
| `devspace-one` | Python service runners; `services/domain_merchant`, `services/apollo_outreach`, `services/devspace_outreach`, Afternic services; existing log files; CRM execution/results APIs | Execution |
| `dsorchestrator` | Python CLI and workers; `core/state.py`, `core/workflow.py`, `core/contracts.py`; local SQLite or shared PostgreSQL; structured completion logs | Workflow coordination |
| `devspace-crm` | Next.js/TypeScript; authenticated decision-engine and feedback-loop route handlers; Supabase migrations | Organizations, approvals, shared durable state, results |
| `schopath` | Flutter app and Supabase schema; `docs/scout-contract.md` explicitly says Scout is a separate service and MMonolith/CRM are not connected | Scholarship business, not a verified DevSpace workflow |
| `DevSpaceOutReach` | Standalone Python outreach pipeline and database code | Separate outreach implementation; not conflated with DevSpace One's service |

No persistent HTTP health server or standard worker heartbeat was found for the four Python engines. dsorchestrator's `health` is a CLI capability/dependency check, not an HTTP endpoint or heartbeat. Monitor does not call it because source CLI initialization is not needed for read-only observation.

## Actual workflow state

`dsorchestrator/core/state.py` defines:

- `workflow_runs`: ID, workflow type, organization, cycle key, status, current stage, correlation UUID, creation/update/completion timestamps, error message and operational metadata.
- `stage_runs`: ID, workflow run foreign key, stage, owner engine, status, attempt, start/end timestamps, input/output reference JSON, error message, plus operational claim/retry fields which the monitor does not select.

Existing local database at `dsorchestrator/data/orchestrator.sqlite3` was readable and held **zero workflow and stage rows**. No replacement source tables were created. Source SQLite is opened with WAL-aware read-only semantics; `immutable=1` is deliberately not used because it could hide committed WAL records.

The inspected `core/workflow.py` declares this domain sequence:

1. `research` — MMonolith
2. `decision` — Decision Engine
3. `approval` — CRM
4. `execution` — DevSpace One
5. `feedback` — MMonolith
6. `updated_intelligence` — MMonolith
7. `redecision` — Decision Engine

Each stage depends on the previous stage. There is no separate measurement or dispatch stage in these declarations. `devspace-services` and `crm-companies` use lifecycle contracts whose business adapters are explicitly not implemented. The registry also has subscriptions. Unknown/new workflow types still render from actual records.

`core/contracts.py` validates explicit output references: intelligence report IDs, recommendation IDs, execution request IDs, execution result IDs and feedback evaluation IDs. Correlation IDs are UUIDs derived from organization/run research identity. Monitor uses those IDs and same-organization foreign keys, never timestamp proximity.

## Existing CRM tables and read APIs

Inspected `supabase/migrations/002_multi_tenant.sql`, `014_decision_engine.sql`, `016_feedback_loop.sql`, `types/organization.ts`, and the two API handlers.

Important existing tables:

- `organizations`, `organization_members`, `organization_services`, `companies`, `business_groups`
- `market_signals`, `intelligence_reports`, `intelligence_report_signals`
- `decision_runs`, `recommendations`, `recommendation_evidence`, `recommendation_reviews`
- `execution_requests`, `execution_results`
- `predictions`, `feedback_evaluations`, `intelligence_report_feedback`
- `bot_runs`, `activity_log`, outreach/lead tables

CRM organizations have UUID, name, slug and type (`devspace` or `customer`). Workflow tenancy uses `organization_id`, not arbitrary company-name matching. Companies and organizations are not interchangeable. dsmonitor labels runs by their exact organization, and only reads remote business context for explicitly configured organization IDs.

Read-only routes already in source:

- `GET /api/decision-engine/organizations`
- `GET /api/decision-engine/context?organization_id=...`
- `GET /api/bot/feedback-loop/context?organization_id=...`

The first context route includes recommendations and requests/results; the second includes explicit recommendation evidence and feedback/report links. Neither exposes complete decision-run history through the inspected context contract. Monitor will show a referenced decision-run ID as UNVERIFIED if its record is not readable through this interface.

These context APIs return full organization context; they are bounded to 4 MB in the monitor and cached, rather than repeatedly downloaded by each browser. Monitor does not use CRM GET routes with names such as `*-next-action`: a GET verb alone is not assumed to make operational dispatch safe.

## Research, outreach and scholarship

MMonolith's `observations.collected_at` and `report_history.generated_at` provide reliable source-specific UTC counts. The local research database also contains Google Play and trend tables. These are not automatically presented as one of the initial workflows: a category name or adjacent timestamp is not a workflow correlation.

DevSpace One's `services/devspace_outreach/README.md` and runner show prospect discovery → website auditing → opportunity scoring → review-ready email drafting → CRM ingestion. A prepared draft is **not** an email sent. There is no complete local, structured daily ledger for all of these actions in the inspected service. Consequently discovered/audited/prepared/sent/response/backlog counters remain unavailable, rather than counting generic stdout lines.

Existing DevSpace One logs contain undated `ModuleNotFoundError: No module named 'core'` traces and an Apollo insufficient-credit response. Their occurrence times and whether they remain current are unknown. The monitor now exposes these actual error summaries and the uncertainty, without making them today's errors or current failures.

Schopath's contract describes scholarship sources, catalog ingestion, verification, eligibility and deduplication, but explicitly states no MMonolith/CRM integration exists. It is registered as NOT CONFIGURED, not simulated as a research/decision/execution loop.

## Real observations and historical evidence

- Local MMonolith database: readable; zero observations and one research report at initial inspection. Extra Google Play/trend tables exist; no total was fabricated by summing unlike records.
- Local dsorchestrator database: readable, zero runs.
- Configured deployed CRM: decision-engine organizations API returned HTTP 404.
- Configured Supabase: initial connection failures, then HTTP 401 from independent PostgREST probe. It is an access failure, not evidence that all engines or the database server are down.
- No engine persistent Python process or heartbeat was established during inspection. Batch engines therefore show UNKNOWN availability.

`dsorchestrator/data/safe_integration_trace.json` exists and lists a seven-stage completed domain test, including explicit report, recommendation, approved request, result, feedback and next recommendation IDs. Its corresponding `docs/VALIDATION.md` says it used synthetic evidence, a temporary PostgreSQL/CRM environment and test execution with no external actions. That artifact was inspected and compared with the source contracts. It was not imported into the dashboard, rerun, or represented as a newly verified live workflow.

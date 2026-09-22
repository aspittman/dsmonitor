# Verification and source comparison

## Validation result — 2026-09-18

- 41 pytest tests passed after the monitoring-access correction.
- JavaScript syntax check passed.
- Chromium desktop (1440 px) and mobile (390 px) checks passed: six cards, five tabs, engine detail, populated workflow filters, failure detail, retry display, HTML escaping, no mobile page overflow and no JavaScript exceptions.
- A scan of 122 locally collected monitoring records found zero exact matches for configured secrets; database permissions were 0600. Redaction patterns and persistence are also covered by tests.
- Real source probes exposed CRM HTTP 404 and independent Supabase HTTP 401 with PostgreSQL 42501 (permission denied). Supabase Auth health returned 200. Monitoring access gaps no longer imply that all engines are degraded; genuine outage tests still pass.
- No live complete workflow or BotMonitor comparison could be verified with the available sources. Optional PostgreSQL transport is implemented; no production PostgreSQL credential/session was exercised.

## Automated checks

Run from dsmonitor:

```bash
./venv/bin/python -m pytest -q
node --check static/app.js
```

The suite covers source write rejection, missing-database non-creation, CRM outage, Supabase outage, simultaneous outages, adapter failure, malformed CRM data isolation, tenant mismatch rejection, tenant filters, output/database redaction, secret formats, opt-in stale thresholds, bounded totals, timestamp offsets, unknown log timezones, undated errors, error-history deduplication, local history failure, cached CRM contexts, API mutation rejection and local-only access.

A seven-stage schema fixture tests source-derived stages, explicit reference resolution and durations. It is synthetic test data in temporary files, never mixed into `data/dsmonitor.db` or an operational database.

With the application running:

```bash
./venv/bin/python scripts/browser_check.py
```

This uses installed Chromium and Playwright, checks cards, navigation, detail views, mobile overflow and JavaScript errors, and writes desktop/mobile screenshots under `docs/`.

## Verify each engine without running it

```bash
./venv/bin/python scripts/verify_sources.py
```

This command performs the same independent reads as the dashboard and prints sanitized evidence. It may write monitoring snapshots to dsmonitor's own database. It never runs source engine commands.

| Engine / dependency | Manual comparison |
|---|---|
| MMonolith | Open engine details; compare the research-store check and UTC counts with read-only SELECTs of `observations` and `report_history`; compare last successful report timestamp with `generated_at`. View existing logs without executing `main.py`. |
| Decision Engine | Inspect an already captured JSON stdout file using `DSMONITOR_LOG_FILES`; compare linked recommendation IDs/statuses in the scoped CRM context; no process found for a batch job is not proof of failure. |
| DevSpace One | Compare displayed error summaries with existing `logs/*.log`; use linked `execution_request_id` and `execution_result_id` for actual executions. Undated errors have N/A occurrence time. Never rerun a service for verification. |
| dsorchestrator | Read `workflow_runs` and `stage_runs` from the selected backend in read-only mode. Verify owner, attempt, timestamps, status, IDs and error message. A readable state database does not prove the worker is alive. |
| CRM | Engine detail shows the authenticated organizations GET result; configure an explicit organization scope to compare context records. HTTP 401/403 means access failure, HTTP 404 means route missing/wrong deployment, and a network timeout means the probe did not reach the endpoint. |
| Supabase | Inspect independent PostgREST/SELECT 1 check. A successful anon-key query verifies that request, not service-role access to all operational tables. A failing CRM probe does not suppress this probe. |

For local SQLite comparisons, use this safe pattern (do not import source `State`, storage classes, or their CLIs):

```python
from pathlib import Path
from adapters.base import readonly_sqlite
with readonly_sqlite(Path('../dsorchestrator/data/orchestrator.sqlite3')) as db:
    runs = db.execute('SELECT id,workflow_type,status,current_stage,updated_at FROM workflow_runs').fetchall()
```

Some restricted execution environments block SQLite's existing WAL/shared-memory access even in read-only mode. Run the same SELECT outside that sandbox with permission; do not bypass WAL using SQLite's immutable mode.

## Verify a complete existing domain workflow

Set `DSMONITOR_ORGANIZATION_IDS` to the organization that owns the existing run. Point the orchestrator adapter at the backend actually used by that run, and configure valid monitoring access to its CRM. Restart dsmonitor after changing configuration.

```bash
./venv/bin/python scripts/verify_sources.py --workflow EXISTING_WORKFLOW_UUID
```

This exits 2 if the run is absent, recorded stages are incomplete, or referenced records cannot be verified. Exit 0 means all recorded stages completed and the referenced records were readable within that tenant. It is not proof of real-world purchases, delivery, or other external side effects.

For the domain loop, independently compare:

1. `workflow_runs.id`, `organization_id`, `correlation_id` and `current_stage` with the detail view.
2. Research stage's output `intelligence_report_id` with CRM `intelligence_reports.id` and its predictions/evidence.
3. Decision stage's `recommendation_ids` with `recommendations.id`. Follow `recommendation_evidence.intelligence_report_id`; do not select a report merely because its timestamp is nearby.
4. Approval stage's `execution_request_ids` with actual request rows. Confirm their `recommendation_id`, `review_id`, `approved_at` and `approved_by` in the source system. Monitor does not copy approval identities into history.
5. Execution stage's `execution_result_ids` with `execution_results.id` and exact `execution_request_id`. Match organization ownership and source status, not a generic “completed” banner.
6. Feedback stage's `feedback_evaluation_ids` with feedback rows referencing that same prediction, recommendation, request and result.
7. Updated intelligence via `intelligence_report_feedback.report_id` / `feedback_id` and `intelligence_reports.previous_report_id`.
8. Redecision recommendation references and their evidence for the updated report.
9. Source error messages, retry count (`attempt - 1` where attempts are present), and each source timestamp against the dashboard.

The monitor labels missing records UNVERIFIED and retains the orchestrator's assertion separately. Do not approve, purchase, dispatch or rerun anything merely to make this check pass.

**Current limitation:** no complete live run was available. The local database has zero runs, the configured CRM monitoring route returns 404, and the independent Supabase credential received 401. The old `dsorchestrator/data/safe_integration_trace.json` was reviewed as historical synthetic integration evidence only. A live end-to-end verification remains pending real source availability.

## Outage and independence checks

The automated tests inject failures independently and assert the dashboard still returns HTTP 200 with all six cards and the unaffected workflow data. The actual deployed route/access errors also leave local research, log errors, orchestrator state and monitoring history visible.

To manually inspect the UI under an unreachable endpoint without touching source systems, set a dsmonitor-only override such as `DSMONITOR_CRM_URL=http://127.0.0.1:1` or `DSMONITOR_SUPABASE_URL=http://127.0.0.1:1`, then restart the monitor. Restore the override afterwards. No operational service is stopped.

Stop dsmonitor with Ctrl+C and confirm independently that the source services continue operating. The architectural guarantee is stronger than a connectivity test: source projects were not edited, do not import dsmonitor, and never call its database or APIs.

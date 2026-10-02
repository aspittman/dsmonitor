# Engine-owned capability reporting — installed 2026-09-25/26

The running dsmonitor instance now consumes real read-only reports from MMonolith,
Decision Engine, DevSpace One and dsorchestrator. Live verification on
2026-09-26 at 06:09 UTC shows **CONNECTED and required reads VERIFIED for all five
Domain Merchant matrix relationships**, including CRM. Overall remains UNKNOWN
because sufficient write/flow/activity evidence is not yet available. This is an
observability improvement, not a claim that a production cycle succeeded.

See [the live API verification](engine-capability-live-validation.json) and
[the exact source-file manifest](engine-capability-change-manifest.json).

## Installed changes

- Each batch engine has an independent `monitoring/capability_probe.py` and a
  `profile.json` naming its actual CRM environment keys and registered inputs.
  It imports no business entrypoint and performs only authenticated GETs and,
  for dsorchestrator, tenant-scoped read-only SELECT LIMIT 1 queries against its
  existing workflow and stage storage. Missing SQLite storage is never created.
- CRM has a new authenticated GET-only
  `/api/bot/monitoring-capabilities?organization_id=...&engine_id=...&service_id=...`.
  It validates the organization, accepts only fixed service/engine/table contracts,
  and runs `SELECT id ... LIMIT 1` per required table. Empty results are successful
  reads; permission errors are failed reads. It uses the existing trusted bot
  authorization/server database client. No new key, privilege, RLS exception,
  database migration, arbitrary-table access or operational mutation was added.
- The deployed CRM currently does not serve that new route. Domain diagnostics
  therefore fall back to the existing authenticated organization context GETs.
  Those routes are bounded client-side to 4 MB and five seconds but paginate all
  tenant records internally. Deploying the new CRM route removes that extra
  historical-read cost. Legacy DevSpace Services lead-read coverage remains
  UNKNOWN until that bounded endpoint is deployed.
- `scripts/engine_capabilities.py` invokes only the new diagnostic commands and
  writes health reports to `dsmonitor/data/capabilities/<engine>.json`. It uses
  the same environment-resolution function as the existing Domain Merchant daily
  launcher for MMonolith, Decision Engine and DevSpace One. dsorchestrator uses
  its own environment. Configuration scope is stated in every report.
- dsorchestrator's previously missing `CRM_API_URL` and `CRM_API_SECRET` were
  filled from the existing daily-job configuration in its private `.env` (0600).
  Existing values were preserved. No credential value was logged or committed.
  This reuses the architecture's existing shared bot credential; it does not
  create separate engine identities or claim the existing credential is
  least-privilege per engine.
- A separate user cron job runs the diagnostics every two minutes. An exclusive
  lock prevents overlap; each worker has a 90-second total timeout and probes
  use five-second HTTP timeouts. Diagnostic output is a timestamped snapshot,
  not operational truth. dsmonitor refreshes its UI on the existing ten-second
  cadence; engine reports expire after 180 seconds. Failed publishers cannot
  leave an indefinitely green cached report.
- Diagnostic process presence does not mark an engine ONLINE. Diagnostic read
  timestamps are not business last-read, last-activity or handoff timestamps.
  Probes never emit business receipts or force `work_expected:false`.

## Real activity receipts

Reference-only, best-effort hooks were added to actual successful operations:

| Owner | Receipt source |
| --- | --- |
| MMonolith | Validated context reads; successful intelligence publication and feedback evaluation |
| Decision Engine | Validated context reads; successful recommendation finalization, retaining metadata workflow context |
| DevSpace One | Successful real request claims and execution-result submission |
| dsorchestrator | Successful persisted stage transition in autocommit; no receipt while a transaction is still open |

Receipts contain only service/engine/organization/table/record IDs, event type,
source timestamp, and existing workflow/correlation IDs when present. They never
include business payloads or credentials. An unavailable receipt sink does not
change an operational result. Logs use nonblocking locking and rotate at 8 MB
with one backup; dsmonitor reads only the bounded current tail.

Missing workflow IDs remain missing. The trace adapter accepts explicit artifact
receipts as uncorrelated source observations; it does not create fake authoritative
workflow IDs or count these receipts as completed workflows. Source receipts can
prove writes or exact-ID reads but cannot complete a workflow stage. A diagnostic
UNVERIFIED write assessment does not erase stronger real persistence evidence.

No business workflow was run to test these hooks against production. Their safety
and linkage are tested with temporary files and mocked clients; they will collect
real evidence when normal authorized engine activity occurs. Existing execution,
no-purchase, test-mode and approval restrictions are unchanged.

## Scheduling and remaining gaps

The existing crontab was inspected: research 07:00, decision 08:00, outreach 09:00
in the host cron timezone. These business jobs were preserved verbatim. Their
existence does not prove execution happened, and they are not a single correlated
workflow. No false schedule-success or no-work-due statement was added merely
because a diagnostic succeeded. Schedule-aware service activity remains UNKNOWN
until an appropriate explicit activity contract and reliable run-start evidence
are available for those independent jobs.

Domain Merchant now has verified current connectivity/reads, but writes and
handoffs still need real observations. In particular, MMonolith's report write
alone does not verify its feedback output; no arbitrary NO_ACTION recommendation
is relabeled as Domain Merchant; no approved execution request, result or feedback
is invented. Fresh stage persistence must occur before dsorchestrator's write
evidence can become VERIFIED. No fake data was inserted to turn cells green.

The independent Supabase monitoring role can still be permission-limited. Working
engine/CRM access is evaluated with its own configured credentials, not inferred
from that monitor role. No database permission was broadened to hide the warning.

## Verification and operation

- dsmonitor: **115 tests passed**.
- MMonolith: **17 focused probe/domain tests passed**.
- Decision Engine: **35 probe/CRM client tests passed**.
- DevSpace One: **15 probe/feedback-worker tests passed**.
- dsorchestrator: **39 tests passed**.
- CRM: new endpoint authorization, tenant scope, bounded-query and permission-error
  tests passed; TypeScript `tsc --noEmit --incremental false` passed.
- All 34 installed engine/CRM source files matched the tested artifact hashes.
- Live diagnostics published reports for all four batch engines. The running
  dsmonitor API shows CONNECTED / VERIFIED reads for all five Domain Merchant
  relationships with no monitor errors.

Only dsmonitor was reloaded to load the new readers. No business engine was
restarted, workflow retried, recommendation approved, email sent, or business
record repaired. The test servers from the prior UI work were not used as
production dependencies.

Open Services → Domain Merchant → any engine badge → Current capability. Reports
should show CONNECTED and VERIFIED reads while preserving UNVERIFIED writes and
UNKNOWN handoffs where appropriate. New real receipts appear in Trace Explorer as
artifact observations and in pipeline evidence when matching IDs exist.

The diagnostic cron command is:

```sh
*/2 * * * * cd /home/aaron/MyBotz/dsmonitor && /home/aaron/MyBotz/dsmonitor/venv/bin/python scripts/engine_capabilities.py > /home/aaron/MyBotz/dsmonitor/logs/engine-capabilities.log 2>&1
```

To run a manual read-only collection: `venv/bin/python scripts/engine_capabilities.py`.
A diagnostic already running holds a lock; a second invocation exits without
starting duplicate probes. An optional `--watch` mode exists, but the installed
configuration uses cron, not an additional persistent engine process.

New monitor settings: `DSMONITOR_ENGINE_CAPABILITY_SECONDS=180` and optional
`DSMONITOR_CAPABILITY_FILES`. Existing shared dependency cache settings remain
independent. Source events in `<engine>/logs/capability_events.jsonl` are discovered
automatically; explicit `DSMONITOR_TRACE_FILES` entries remain supported.

Original changed source files and the original crontab are backed up under
`/tmp/devspace-capability-upgrade/originals` (temporary storage). The installation
manifest is retained in this repository. The dsorchestrator `.env` addition and
one cron entry are configuration changes in addition to the 34 listed files.
No operational database migration or remote CRM deployment was performed.

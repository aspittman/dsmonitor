# Operational rollout — October 5, 2026

Infrastructure and the supported zero-spend workers are configured. A complete live
review/feedback cycle remains pending a specific human approval in CRM. Research
adapter availability is verified separately from successful business execution.

## Completed

- Audited production through the existing authenticated Supabase CLI and scoped
  CRM reads. Migrations 001–025 were already applied; none were replayed.
- Repaired and deployed CRM monitoring scopes for DevSpace Services, Schopath and
  Investorpath orchestration. Stage reads join their workflow for tenant ownership;
  `stage_runs` has no `organization_id` column.
- Aligned client-brief monitoring with requests, research, evidence links and
  results. Every read is bounded and organization scoped.
- Added migration 026 and a dedicated `dsorchestrator_runtime` database login.
  RLS permits workflow/stage operations for the eight configured organizations,
  plus backend-only client fanout parents. The role cannot write approvals,
  recommendations, execution requests/results or research. Its organization
  allowlist is administrator managed in `orchestrator_organization_scope`.
- Configured dsorchestrator's SSL database connection in its private `.env`.
  Domain, service and product capability checks use shared PostgreSQL. Local
  engine invocation remains enabled.
- Restored the already-applied migration 025 from Decision Engine into CRM's
  migration directory so repository history matches production.
- Registered product research workflow identities and dsorchestrator participation.
- Enabled only `review_domain_evidence` for Domain Merchant and
  `prepare_client_outreach` for client services. Human approval remains required;
  the workers enforce zero spend and prohibit external calls, sending and purchases.
- Fixed Decision Engine duplicate suppression: explicitly non-executable advisory
  assessments no longer suppress executable research reviews. Legacy and executable
  active recommendations retain their duplicate guards.
- Installed `scripts/approved_workers.py` every 15 minutes in the existing user's
  crontab. It runs the approved domain-review worker, domain outcome ingestion and
  client-brief workers for the six configured clients. Existing schedules/settings
  were preserved. Cron is active. An exclusive lock prevents overlapping launcher
  cycles; worker outboxes retain their existing replay protection.

CRM commits: `c895dc1`, `239ac62`. Decision Engine commit: `353e66c`.
Both repositories were pushed to their existing `master` branches. DevSpace One's
monitoring profile is updated locally; its other pre-existing uncommitted work was
preserved. Dsorchestrator is a local repository without Git metadata.

## Verification

- CRM API suite: all six test files passed; TypeScript check passed.
- Disposable PostgreSQL: nine domain-review, client-brief and runtime-isolation
  integration tests passed using the complete restored CRM migration history.
- Domain-review worker: eight tests passed.
- Orchestrator service/product/review bridge: eleven tests passed.
- Decision Engine: 100 passed, 18 database-dependent tests skipped. The separate
  CRM PostgreSQL integration tests above exercised approval/result/feedback contracts.
- Dsmonitor: 152 passed.
- A rollback-only production transaction verified scoped workflow/stage writes
  and denial of approval writes before the role was provisioned.
- All four service/product research workflow dry runs showed research and decision
  adapters AVAILABLE with shared persistence. No provider collection was invoked.
- Live approved workers returned IDLE for domain review and all six client brief
  queues; domain learning returned NO_NEW_FEEDBACK. This verifies reachable worker
  paths, not a completed execution.
- The local dashboard `/healthz` returned HTTP 200.
- Final sanitized reads are recorded in `operational-readiness-audit.json`; engine
  capability snapshots remain in `data/capabilities/` and expire normally.

## Next human checkpoint

Decision run `365f0b61-d466-4768-821f-f9feeb257476` completed without errors and
created one actionable recommendation:

- Organization: `06eaf14d-a535-4ccc-ad17-286da58d3fdd` (Domain Merchant).
- Recommendation: `411b6655-c624-4d03-83c8-e7fec6e729a0`.
- Display title: Market Research.
- Action: `review_domain_evidence`; budget: 0.
- Exact research report: `57c52331-fbaa-4b01-9b9b-a24190d987d9`.
- Observed status: RECOMMENDED, awaiting human approval.

After finishing CRM login, inspect and approve this specific review if desired.
The scheduled worker can then process its authorized request and ingest feedback.
The existing next research job incorporates feedback. Validate the actual request,
result, feedback and next-report IDs afterward; no future outcome is asserted here.

## Remaining service work

- The owner confirmed there are no student/company profiles or source exports yet.
  Schopath and Investorpath personalized matching therefore remain pending real
  inputs. Discovery leads must retain their unverified source/eligibility status.
- Schopath app data transport and Investorpath's unconfigured backend repository
  remain separate from CRM research orchestration. Investorpath still needs its
  app authentication, profile persistence and opportunity transport implementation.
- Domain acquisition still lacks qualifying demand, buyer and current complete
  registrar checkout-quote evidence. Review readiness does not enable purchases.
- DevSpace Services has research/advisory and legacy ingestion paths, but no ready
  CRM request-driven execution adapter for that service. Its DevSpace One execution
  capability remains blocked; no unsupported adapter was advertised as ready.
- Production purchases, email delivery and other planned service actions require
  their actual implementations and explicit authorization. This rollout adds no
  paid data collection or new research-provider schedule.

## Maintenance

Run `venv/bin/python scripts/operational_readiness_audit.py` for a read-only audit.
Run `venv/bin/python scripts/approved_workers.py --dry-run` to inspect the worker
plan. Worker outcomes appear in `logs/approved-workers.log`, without raw payloads.
Use the private `.env` for the runtime credential; it is not committed or printed.

The cron inspection accidentally exposed an existing SMTP app password in tool
output. Rotate that app password and update its existing configuration. The value
is not reproduced in this report or the sanitized audit. Temporary credential files
created during provisioning are removed after final verification; private backups
of the prior environment and crontab are retained for rollback.

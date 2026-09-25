# DevSpace architecture standardization — 2026-09-24

## Scope and evidence

The actual folders are `/home/aaron/MyBotz/{mmonolith,decision_engine,devspace-crm,dsorchestrator,devspace-one,dsmonitor}`. Five are Git working trees; dsorchestrator has no Git metadata. Existing uncommitted work was inspected and preserved. See `audit.md` for the required pre-change classification.

A read-only request to the configured Supabase PostgREST OpenAPI confirmed the shared intelligence, recommendation, approval, execution and feedback tables. Workflow/stage tables and the service catalog were not exposed. `deployed-schema.json` records column names only, without credentials or customer rows. This is not a PostgreSQL catalog/RLS inspection: deployed policies, indexes and migration history still require administrator verification before migration. No production migration or business action was performed.

## 1–8. System responsibilities and actual integration

| System / responsibility | Reads | Writes / tables and APIs | Services and identity | Changes |
|---|---|---|---|---|
| MMonolith: research, observations, predictions and learning | Source/provider observations; CRM report, prediction, result and feedback context | Local specialized observation/cache history; CRM `market_signals`, `intelligence_reports`, report/signal links, `predictions`, `feedback_evaluations`, report/feedback links through `/api/bot/feedback-loop/{intelligence,evaluations}` and `loop_publish[_research]` / `loop_evaluate` | Working shared domain reference; separate demand/trends/Google Play research remains specialized. Optional explicit workflow context in `LoopClient.publish`; orchestrated publishing attaches the same run ID and correlation. Tenant context is checked before publish and again by SQL. | Added optional context propagation without mutating caller bundles. Research and evaluation algorithms unchanged. |
| Decision Engine: scoring, constraints, strategy and recommendations | `/api/decision-engine/context`: organization configuration, signals, reports, constraints, historical outcomes and active recommendations | `decision_runs`, `recommendations`, `recommendation_evidence`, dependencies via existing run/finalization API and RPCs. No approval or action client added. | Domain acquisition, outreach, Google Ads, landing pages, SEO and NO_ACTION strategies remain. Strategy/action adapter names are distinct from business service identity. Optional workflow context follows recommendation metadata and decision snapshot; `decision_run_id` remains a separate evaluation ID. | Added optional validated context parameter to DecisionService; recommendation context is persisted and checked by CRM. |
| DevSpace CRM: authenticated access, presentation, review and shared APIs | Existing customer/business data and normalized shared records | Existing server APIs persist engine-owned data on behalf of engines; authenticated `de_review_and_request` records review and execution authorization | Registry lists five canonical services; `organization_services` still configures tenant execution adapters. User sessions/RLS protect reads; trusted bot endpoints still require their existing shared secret. | Service summary page and navigation; legacy lead routes now require a session, use the session client/RLS, and restrict mutations to admins; new notes/activity preserve lead organization. |
| Supabase: durable system of record, integrity, locking and tenant access | Not an engine; serves authorized reads and RPCs | Existing concept tables plus catalog/aliases; reuses the existing orchestrator workflow/stage definitions | Root evidence and recommendations have explicit service/run identity. Results, predictions and feedback resolve it through existing same-tenant links. New context must match persisted workflow organization, service, parent, correlation and intended producer. | Two additive migrations; no deleted records, renamed tables or rewritten legacy lineage. Added tenant policies on legacy tables and security-invoker lineage view. |
| dsorchestrator: coordination, waiting, dispatch, retries/reconciliation | Persisted stages, CRM approval/request context, DB service registry in shared mode | Existing `workflow_runs`, `stage_runs`; persisted stage payloads and reference-only results; local outbox receipts | Domain has actual adapters with test-only execution; devspace-services/crm-companies/subscriptions remain declarations with unavailable real adapters. Same run ID in every payload; tenant ID retained. Optional backend-only parent links separate per-organization child IDs. | Service resolution; context in research/decision bridge; additive local SQLite identity columns; parent creation and `--parent-cycle`; expanded contract/reference tests. No research/scoring/action code moved here. |
| DevSpace One: execute approved work and report results | Claimed request, approval-derived parameters, authorized MMonolith report/candidates | Existing `execution_results` through `/api/bot/feedback-loop/results` / `de_record_result`; legacy outreach delivery records remain | Domain reference is approved test investigation only; existing Apollo/DevSpace outreach remains separate legacy behavior. Structured result echoes run/service/org context from approved research; SQL lineage uses authoritative request→recommendation links. | Context retained in test result; existing no-purchase/no-outreach guards preserved. |
| dsmonitor: independent observation and diagnosis | Read-only orchestrator PostgreSQL/SQLite, scoped CRM GETs, source logs/optional JSONL traces, health probes | Only monitor-owned local snapshots/events. No operational table or source-state writes. | Explicit service/parent columns read when present, old schemas still accepted; typo alias normalized. Run ID and tenant scope drive trace grouping. | Optional-column discovery, parent/service propagation, alias compatibility, regression test and read-only scratch-run verification script. No operational dependency on monitor. |

## 9–15. Schema, retained structures and ownership

Reused: `organizations`, `organization_services`, `profiles`, companies, contacts, leads, sales records, organization memberships/groups, notes/activity, execution capabilities and every existing loop table. `workflow_runs` and `stage_runs` retain their existing schema/ownership; CRM migration 019 creates those same tables only if missing. It does not create a parallel queue or another workflow model.

New tables: `service_registry` and `service_aliases`. New view: `service_record_lineage`, using `security_invoker=true` so source-table RLS applies. It is a relational projection, not another history store.

New columns: `workflow_runs.service_id`, `workflow_runs.parent_run_id`; `intelligence_reports.service_id`, `intelligence_reports.workflow_run_id`; `recommendations.service_id`, `recommendations.workflow_run_id`. Descendant records do not receive redundant context columns. Existing metadata carries the full context envelope. Workflow organization becomes nullable only for an explicitly marked backend-only CRM-company parent; customer child work still has a real organization.

New CRM migrations: `019_service_context.sql`, `020_legacy_tenant_reads.sql`. Existing migrations are not rewritten. Migration 019 adds lookup indexes, registry references, parent references, identity validation/immutability and the lineage projection. Migration 020 enables missing RLS coverage, retains admin management, restricts customer reads to their organization, and grants no anonymous access to those tables.

| Important shared table | Primary writer / authority |
|---|---|
| organizations, companies, contacts, leads, sales_records | CRM tenant/admin operations and existing authenticated ingestion adapters; ownership belongs to CRM business records |
| organization_services, organization_members, organization_business_groups, profiles | CRM administration / identity infrastructure |
| service_registry, service_aliases | CRM schema/configuration administrator; not strategy engines |
| decision_constraints | CRM/operator-provided customer constraints |
| market_signals, intelligence_reports, intelligence_report_signals | MMonolith for the shared research loop; legacy imports retain their original provenance |
| predictions | MMonolith |
| decision_runs, recommendations, recommendation_evidence, recommendation_dependencies | Decision Engine |
| recommendation_reviews | Authenticated CRM admin approval layer |
| execution_capabilities | Execution integration/operator configuration |
| execution_requests | CRM approval/workflow layer; DevSpace One gateway may atomically claim authorized work |
| execution_results | DevSpace One through the result RPC |
| feedback_evaluations, intelligence_report_feedback | MMonolith |
| workflow_runs | dsorchestrator |
| stage_runs | dsorchestrator and authorized participating stage infrastructure |
| activity_log, lead_notes, bot_runs | Existing CRM operations / authenticated legacy producers |
| trace events | Participating source instrumentation; dsmonitor only observes and stores its own monitoring history |

Retained legacy structures: specialized domain portfolio/intelligence projections, outreach state, local research/cache databases, local SQLite development coordination, older adapter names, decision-engine migration 014 test fixture, and existing API routes. Nothing was dropped or formally deprecated. Existing source_engine/created_by/source fields and historical IDs retain their meaning. Unknown legacy lineage remains unknown.

## 16–18. Service, workflow and parent identity

Canonical business services are `domain_merchant`, `scholarship_research`, `devspace_services`, `devspace_clients`, and disabled future `investor_research`. Database catalog is authoritative. `contracts/services.json` is a checked/tested local-development snapshot; shared orchestrator mode resolves the database catalog. Engines receive context instead of importing dsmonitor or one another for identity.

Aliases retained: `domain` → domain_merchant; `scholarship` and `scholorship_research` → scholarship_research; `devspace-services` → devspace_services; `crm-companies` and `crm_business` → devspace_clients. `subscriptions` is NOT silently relabeled scholarship because the existing declaration does not establish that equivalence. Existing adapter keys (including outreach providers) remain valid and are not rewritten into business-service names.

`workflow_runs.id` is the canonical end-to-end workflow_run_id. Existing correlation UUID is preserved as a companion identity. Stage IDs, decision_run_id, report run_key, recommendation IDs and execution-request IDs remain distinct references; no per-boundary workflow IDs are generated. Context includes service/run/org/parent/correlation and the actual participating engine. The database rejects mismatched context. Legacy callers without context still work and remain visibly uncorrelated.

`crm-companies --parent-cycle <stable-key>` creates/reuses a backend-only parent containing no customer payload. Each organization gets its own child ID, tenant data and stage rows, with the same parent_run_id. Existing unparented cycles are not silently reparented. An old SQLite file with NOT NULL organization_id is not destructively rebuilt: parent fanout requires shared PostgreSQL or a new development DB. The parent currently groups runs; it is not a business execution stage or a complete automatic aggregate-status controller. Scheduled legacy fanout remains unparented unless explicitly adapted to this API.

## 19–22. Lineage and duplicate prevention

Recommendation evidence continues to reference same-tenant signals/reports/results; constraint snapshots are retained in decision_runs. Predictions remain attributable through their report rather than fabricated direct recommendation edges. Approval reviews preserve original/approved parameters and reviewer identity. An execution request references recommendation and review; one request per recommendation and one result per request are enforced by existing uniqueness constraints.

Feedback validates prediction, report, recommendation evidence, request, result, subject, test/live mode and measurement window. It appends a feedback row; new intelligence links previous_report_id and feedback IDs. No historical backfill guesses were made.

Existing tenant locks, FOR UPDATE/SKIP LOCKED claims, stage compare-and-set tokens, stable cycle/run keys and outbox result receipts remain. Ambiguous RUNNING work is reconciled rather than automatically reclaimed. This prevents concurrent duplicate claims; it does not promise exactly-once delivery to an external provider. Future live email/purchase adapters still need provider idempotency or durable delivery reconciliation. Live execution was not enabled.

## 23–26. Isolation, tracing, communications and remaining gaps

New context must match the authoritative workflow tenant, canonical service, parent and correlation. Existing composite tenant FKs remain. Legacy RLS additions hide unknown-tenant records from customers; administrators retain access. Anonymous generic lead endpoints no longer bypass RLS with service-role reads. Admin mutations preserve tenant ownership. No existing RLS policy was loosened. Explicit customer sales writes check tenant ownership and any referenced lead.

Trusted engine APIs still share BOT_API_SECRET/service_role. Primary writers are enforced through application boundaries, context validation and RPC contracts, not fully separated database credentials per engine. A compromised trusted credential remains a cross-engine/cross-tenant risk; credential segmentation is an outstanding deployment project. The local monitor is an owner/admin tool, not a customer portal.

No second tracing system was introduced. dsmonitor reads the existing workflow/stage state and normalizes it into its existing trace model; source JSONL remains optional. Tests cover Workflow/Engine trace behavior, service × engine matrix, NOT_REACHED versus FAILED, waiting/stalled distinction, cut-off and root-failure attribution. Parent IDs are passed through without fetching another tenant's child records. Source stage tables retain only the latest attempt, so complete historical attempt visibility still depends on retained source events/monitor observations.

Direct communication retained: documented CRM server APIs and the orchestrator's scoped local subprocess bridge. Dispatch inputs/claims precede invocation; outputs/reference receipts are persisted. The shared production worker pattern consumes durable stage state. Engines do not depend on CRM browser rendering or dsmonitor, but CRM APIs share the Next.js deployment: a full API-server outage pauses work. Independent API hosting is not introduced in this change.

Remaining inconsistencies are explicit: non-domain real service adapters are missing; standalone legacy jobs can remain without workflow context; demand/trend aggregates do not all have shared ingestion endpoints; older outreach flows have their own existing authorization/delivery contracts; per-engine least-privilege credentials are not implemented; deployed RLS/index/migration catalog requires administrator comparison; parent aggregation and automatic scheduled fanout are limited; full historical attempt events are not durable in stage_runs alone. These are not represented as completed production capabilities.

## 27–29. Migration/deployment order and safe validation

1. Verify actual production migration history and schema against CRM 001–018. The OpenAPI snapshot is insufficient to prove RLS, constraints or prior migration application. Back up using the established Supabase process; do not blindly replay numbered migrations already applied.
2. Apply CRM **019_service_context.sql**. Existing orchestrator 001 may already be present; 019 reuses its workflow/stage tables. Confirm no unrelated tables use those names before applying. PostgreSQL 15+ is required by the security-invoker view.
3. Ensure dsorchestrator **002_exact_test_claim.sql** is applied after the existing CRM loop migrations. Existing orchestrator 001 is only needed on older installations without 019; its IF NOT EXISTS definitions are compatible if already applied. Do not duplicate decision_engine's copied 014 migration.
4. Deploy the CRM API authorization fixes together with **020_legacy_tenant_reads.sql**. Check contacts/notes with null organization ownership: they remain admin-only until reliably attributed. Test admin and two separate customer sessions. Inspect any additional deployed permissive policies: a new RLS policy cannot neutralize an unrelated existing permissive policy.
5. Deploy MMonolith, Decision Engine and DevSpace One context-capable code. Optional arguments/metadata retain compatibility with older callers. No adapter is enabled by this deployment.
6. Deploy dsorchestrator last among operational participants; configure shared PostgreSQL, not local SQLite, for distributed work. Its new code requires migration 019 and the updated DecisionService signature. For local development provide the catalog snapshot through `DEVSPACE_SERVICE_CATALOG` if repositories are not siblings.
7. Deploy/restart dsmonitor independently. Old and new source schemas remain readable. Keep its database connection read-only and its organization allowlist explicit. Configure source event capture separately if full retry history is required.
8. Run the isolated tests before enabling any live adapter. Keep DEVSPACE_ENV=test and fixture research. The domain harness creates its own database, CRM instance and simulated admin session; it does not use production credentials.

Safe domain reference command, from dsorchestrator with the repositories/dependencies installed:

```bash
python scripts/safe_integration.py \
  --engine-root ../decision_engine --postgrest /path/to/postgrest \
  --mmonolith-root ../mmonolith --crm-root ../devspace-crm \
  --devspace-one-root ../devspace-one --monitor-root ../dsmonitor
```

Generic second-service test: `python -m pytest -q tests/test_control_plane.py`, including `test_second_service_contract_preserves_context` and `test_service_identity_and_parent_children`. These use fixture engines to validate identity, approval gating, parent isolation and all coordination stages for devspace_services/devspace_clients. They do not assert that those services have real production business adapters.

Database tests: CRM `python -m pytest -q tests/test_decision_database.py`; CRM `npm test` and `npm run typecheck`; Decision Engine full pytest suite; MMonolith domain tests; DevSpace One feedback worker tests; dsmonitor full pytest suite. Test fixtures now explicitly supply the registrar and price cap required by the already-existing migration 018; production approval/price policies were not relaxed to make tests pass.

See `validation.md` for executed checks and results. Migrations are supplied for manual deployment and were not applied to production.

## 30. Adding investor_research

The canonical disabled service already exists in the registry. Add its declarative workflow type/stages, map it in the catalog snapshot, and test catalog/database agreement. Implement MMonolith research/predictions and feedback, a Decision Engine strategy producing evidence-linked recommendations, and a DevSpace One adapter for a narrowly defined approved action. Reuse constraints, approvals, execution requests/results, workflow/stage state and tenant FKs. Add specialized investor domain records only where the domain requires them; join them to report/workflow/organization identity. Preserve the incoming workflow context at every boundary. Add monitor expectations through its existing registry configuration, then run the same isolated lifecycle and two-tenant tests. Enable the catalog entry, tenant service configuration and execution capability only after the real adapter is verified. Registration alone never authorizes execution.

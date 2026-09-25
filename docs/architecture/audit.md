# DevSpace architecture audit — 2026-09-24

This inventory precedes implementation. Sources are the working trees in `/home/aaron/MyBotz`; pre-existing uncommitted changes are part of the inspected implementation and must be preserved. dsorchestrator is a directory without Git metadata. Deployed Supabase schema has not been verified; migration files are the authoritative inspected source, not proof of deployment.

| Concept | Classification | Evidence / smallest required change |
| --- | --- | --- |
| Business-concept shared schema | ALREADY CORRECT | CRM migrations 014–017 define market_signals, intelligence_reports, predictions, recommendations, recommendation_evidence, recommendation_reviews, execution_requests/results, feedback_evaluations and link tables. Reuse all. |
| Decision ownership | ALREADY CORRECT | DecisionService reads context and finishes recommendation transactions. No approval/action client in active CLI. |
| Research and learning ownership | PARTIALLY IMPLEMENTED | MMonolith domain research and learn own the new loop. Older local demand/trends pipelines remain specialized and publish only aggregates; not all have CRM ingestion. |
| Execution ownership | PARTIALLY IMPLEMENTED | DevSpace One approved domain test worker and legacy outreach exist. Generic production execution adapters are not implemented. Do not pretend tests enable live execution. |
| Approval lineage | ALREADY CORRECT | CRM de_review_and_request requires authenticated admin, records immutable review and creates one request per recommendation. |
| Recommendation evidence | ALREADY CORRECT | Same-tenant composite FKs, evidence required at finalization, dependencies, frozen reviewed evidence; constraints snapshot retained in decision_runs. Predictions reachable through report, not a separate invented link. |
| Feedback lineage | ALREADY CORRECT | loop_evaluate validates prediction/report/recommendation/request/result attribution, subject, time and test mode. New reports reference previous report and feedback links. |
| Claims and idempotency | ALREADY CORRECT | Tenant locks, skip-locked request claims, one result/request, stable report run_key, permanent stage claims and explicit ambiguous-outcome reconciliation. No new queue. |
| Central service identity | MISSING | organization_services is per-tenant execution configuration; execution_capabilities is adapter readiness; monitor registry is observational. None is a business-service catalog shared by engines. |
| Legacy service names | LEGACY | domain, devspace-services, crm-companies, scholarship monitor alias. Preserve these. scholorship_research should resolve to scholarship_research. subscriptions is a distinct declared workflow, not proven scholarship. |
| Workflow context | PARTIALLY IMPLEMENTED | workflow_runs.id follows persisted stage payloads; separate correlation UUID reaches domain reports/recommendation parameters/results. workflow_run_id itself is lost entering engine records. Normalize context without renaming decision_run_id or run_key. |
| Parent/child runs | MISSING | CRM-company iteration creates separate tenant runs without persisted common parent. Cross-tenant parent must contain no customer payload and remain backend-only. |
| Shared coordination | PARTIALLY IMPLEMENTED | Orchestrator PostgreSQL backend supported, SQLite local fallback. Production must use shared PostgreSQL; staged subprocess handoffs are already persisted. |
| Trace architecture | ALREADY CORRECT | dsmonitor reads workflow/stage rows and explicit JSONL events; no operational imports/calls to dsmonitor. Keep derived tracing and helper contract; do not add competing trace store. |
| Historical stage attempts | PARTIALLY IMPLEMENTED | stage_runs overwrites latest attempt; logs may retain prior events. Full durable attempt history is not established by current schema. |
| CRM business presentation | PARTIALLY IMPLEMENTED | Customers/leads/recommendations/domain portfolio/insights exist. Add service summary navigation without rebuilding existing pages. |
| Tenant isolation, new loop | ALREADY CORRECT | Explicit org filters, tenant-response validation, composite FKs, authenticated tenant reads and admin review, server-only mutations. |
| Tenant isolation, legacy CRM | CONFLICTING | Checked-in 001–018 leave organizations/organization_services/contacts/sales_records/notes/activity and membership tables without complete RLS coverage. Audit current queries before additive restrictions; never weaken existing policies. |
| Machine authorization boundaries | PARTIALLY IMPLEMENTED | Bot routes share BOT_API_SECRET/service_role. Application ownership is separated, but a compromised trusted credential is not confined to one engine's writer rights. |
| CRM availability independence | PARTIALLY IMPLEMENTED | Engines use CRM server APIs, not browser UI. APIs share Next.js deployment; frontend rendering is not required, whole server outage pauses persisted workflow. |
| Second service lifecycle | MISSING | devspace-services and crm-companies are declared contracts with unavailable real adapters; scholarship has no implemented engine path. Validate generic coordination honestly; do not fabricate business execution. |

Implementation priorities: additive business-service registry; explicit workflow context through existing metadata/lineage; parent references using existing workflow storage; monitor alias compatibility; tenant policies after query review; service-oriented summary. Retain existing APIs, legacy IDs, specialized domain tables, claims, approval policy and tracing.

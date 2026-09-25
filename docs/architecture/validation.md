# Validation evidence

All operational tests used temporary repository copies and disposable local data. No deployed migration, live provider, purchase, email or customer action occurred.

- Domain lifecycle: actual MMonolith → CRM/Supabase → Decision Engine → real CRM approval form → dsorchestrator → DevSpace One test execution → CRM result → MMonolith feedback/new intelligence → Decision Engine. Seven stages completed. Same workflow and service identity asserted across the relational lineage projection and result envelope. Original report/prediction stayed immutable. Exactly one result per request.
- Domain workflow: `48e74d65-9f08-4ec3-9851-8677833c8be8`. Complete synthetic references are in `domain-reference-trace.json`.
- Monitor: independent read-only PostgreSQL adapter normalized the actual fixture to seven completed stages and fourteen trace events, with duration and no root failure. Monitor was invoked only by an optional test-harness check after operational completion.
- CRM UI: real admin recommendation rendering and form approval, existing domain portfolio, and new service page were checked through the local Next.js server.
- Existing actual PostgreSQL competing stage claims, retry and stale-token protections passed in the integration harness.
- Second service: `devspace_services` fixture lifecycle checks every stage's service/run/organization context; `devspace_clients` tests two tenant children under one backend-only parent. These are contract tests, not a claim of implemented real business adapters.
- Decision Engine: 71 tests passed, including database approval/idempotency/tenant tests.
- MMonolith: 18 focused domain research/learning/context tests passed.
- DevSpace One: 4 approved-test worker tests passed, including no-action guards and context retention.
- Orchestrator: 28 tests, including parent identity and adopting an already-published workflow without creating a second run.
- CRM database: 12 additive migration/RLS/context/parent tests passed.
- CRM TypeScript check and both Node API test files passed; monitor full suite: 65 passed.

Initial test failures were corrected before application: new SQL CASE syntax, bridge context variable shadowing, and older synthetic fixtures that no longer met existing registrar/checkout-price policy. Production strategies and approval constraints were not relaxed. Temporary package namespace pollution was removed; it was not an application change.

Deployed schema inspection used GET of PostgREST OpenAPI only. It proves exposed table/column presence, not deployed RLS, indexes, constraints, or migration history. Those must be checked by the database administrator before applying the supplied migrations.

Final checks: CRM database 12 passed; dsmonitor 65 passed; orchestrator 28 passed; CRM TypeScript typecheck passed and both Node test files passed. The last catalog change adds resolution by the registry's workflow_type so a new registered workflow does not require hard-coded aliases; its database test passed before application.

Application: all 25 reviewed sibling-repository files were applied and verified by SHA-256. Prior file contents were backed up under `/tmp/devspace-architecture-originals`. Existing unrelated work was preserved. No Git commits, pushes, deployments or production migrations were performed.

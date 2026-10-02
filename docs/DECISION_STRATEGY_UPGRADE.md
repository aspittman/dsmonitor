# Decision strategies and first production review cycle

Implemented September 26, 2026 in the existing five repositories. This is an additive upgrade: existing marketing strategies, the test investigation worker, approvals, trace explorers and monitoring remain. No live migration, CRM deployment, business run, approval, purchase or outreach was performed.

## What now makes decisions

Decision Engine already used deterministic strategy evaluation, client constraints, evidence, confidence and a budget-aware planner. It now has the requested service directories under `decision_engine/strategies/`:

| Service | Policies |
| --- | --- |
| domain_merchant | acquisition, pricing, outreach; plus production evidence review |
| devspace_services | prospect, audit, outreach |
| scholarship_research | quality, eligibility |
| devspace_clients | opportunity, optimization |
| investor_research | investor_match, opportunity |

Domain acquisition now uses demand 20, commercial intent 20, comparable sales 15, buyer density 15, historical performance 15, trend 10 and brandability 5. It subtracts trademark conflict 100, excessive acquisition price 20, weak observed buyer pool 15, and poor sufficiently sampled results 15. Existing evidence, freshness, confidence, budget and client-policy vetoes remain. Unknown inputs are listed and earn no invented points. Pricing reports observed comparable statistics, not a fabricated sale forecast. Configuration, normalization rules and input contracts are documented in `decision_engine/SERVICE_STRATEGIES.md`.

The other service policies produce actionable **advisory assessments**, stored in `decision_runs.output_summary.service_assessments`, with scores, confidence, evidence IDs, missing inputs and gates. They do not silently register unsupported execution adapters. Input signals must explicitly match the service and subject. Scholarship eligibility, for example, requires explicit criteria/deadline checks; investor matching requires a verified mandate. Those services still need real evidence and their own execution integrations before becoming operational.

## A useful first cycle without fake business activity

Acquisition qualification remains blocked by missing market evidence. A distinct zero-spend research-review action can nevertheless do useful work:

1. MMonolith publishes actual research, including known gaps.
2. Decision Engine proposes `MARKET_RESEARCH / review_domain_evidence`, linked to that exact report, after CRM advertises the adapter as ready.
3. A human approves it in CRM. Zero budget is permitted only for this explicitly constrained review action.
4. DevSpace One claims that approved production request and reviews its existing candidate records. It returns actual findings, missing inputs and observed counts. It calls no external provider and performs no purchase or outreach.
5. MMonolith consumes the result and appends `OUTCOME_REVIEW` feedback with its exact report/recommendation/request/result IDs. It does not invent a prediction, call one supported, or raise market confidence.
6. The next research report links this feedback and surfaces the remaining evidence gaps.

This gets the data cycle started; it does not solve missing demand, buyer or quote evidence. Review completion means the records were reviewed, not that a domain is a good purchase. Review recommendation confidence describes whether reviewable records exist, separately from acquisition confidence.

The standalone worker supports an organization lock and durable result outbox, safe replay using existing request idempotency, and resuming a claimed pure review. dsorchestrator supports exact-ID production review claims while preserving its test-only acquisition path. Production workflow output includes only the supported review action, not an unsupported acquisition execution.

## Rollout still required

The following steps affect live operation and have **not** been run:

1. Apply `devspace-crm/supabase/migrations/021_domain_evidence_review.sql` through the normal database migration process. It updates approval/queue handling for zero-spend reviews, adds constrained `loop_claim_review` and `loop_observe_review` functions, and extends the existing feedback ledger with an `evaluation_kind`. Existing prediction evaluations keep their required prediction IDs and behavior. The migration does not mark any adapter ready or approve records.
2. Deploy the updated CRM code. It includes authenticated `claim-review` and `observe-review` routes; also deploy the previously added bounded monitoring-capabilities route.
3. Register **only the production action you intend to enable** in the CRM capability registry. For a review-only rollout, the concrete configuration is:

   ```sql
   UPDATE execution_capabilities
   SET status = 'AVAILABLE', adapter_ready = true,
       allowed_actions = ARRAY['review_domain_evidence'], updated_at = now()
   WHERE service_key = 'domain_merchant';
   ```

   This registry is shared across organizations. The review-only action list intentionally does not advertise the old test investigation as production-ready. Retain/use the old action in a separate test environment as appropriate. Normal service enablement and per-organization human approvals still apply.
4. Let the normal scheduled decision job run, or deliberately run the existing `scripts/domain_daily.py decide` command. It will then be able to propose the zero-spend review. Existing active recommendations are not automatically deleted or overridden.
5. **Approve the specific research-review recommendation in CRM.** Neither dsmonitor nor any engine receives permission to approve it automatically.
6. Process it with the new `venv/bin/python scripts/domain_daily.py review` command from dsmonitor's repository. This explicit business launcher invokes DevSpace One's review worker and MMonolith learning; it is not a monitoring probe. No new business cron entry was installed. The existing next research job incorporates the feedback, or an appropriately configured dsorchestrator workflow can coordinate the full path.

Existing engine credentials are reused; no new secret is required for this zero-spend review. Remote/long-running deployments need their updated code deployed as well. No automatic business-engine restart was performed.

## Inputs needed later for acquisition

- Real keyword-demand evidence (`demand_file`), or a deliberate opt-in to the existing billed DataForSEO collector (`with_keywords: true`) with its account configured.
- Real, attributed potential-buyer samples (`buyers_file`).
- Fresh, complete GoDaddy checkout quotes within the configured cap (`quote_file`). A new bounded organization/subject-scoped export loader preserves registrar and total-price provenance. It does not claim to be a new GoDaddy API integration. The legacy static availability importer discarded these fields, so enabling it alone could never pass the intended check.
- Optional sourced scoring assessments (`assessment_file`) for commercial intent, history, trend and brandability. No missing metric is fabricated.
- Actual candidate/sales coverage for mortgage, roofing and tools; the audited reports currently have none.

Input formats are documented in `mmonolith/DOMAIN_AUTHORIZED_INPUTS.md`. The new quote/assessment loaders make the configuration usable, but cannot create evidence that does not exist. Purchasing and outreach remain separate future capabilities with their own approvals.

## Verification

- Decision Engine: 74 tests passed, including scoring, risk vetoes, stale/future evidence, service isolation, eligibility gates and adapter-readiness checks. After the final test/production separation tightening, the nine affected strategy tests passed again.
- DevSpace One: 23 focused tests passed, including production review guards, tenant/lineage checks and identical-result replay after an ambiguous response.
- MMonolith: 30 focused tests passed, including attributed checkout imports.
- dsorchestrator: existing 39 tests passed; a new isolated production-bridge test also passed using the actual review worker and mocked CRM transport.
- CRM: 15 disposable PostgreSQL tests passed, including the full approval→claim→result→feedback→new-report link, repeat-submission idempotency, tenant rejection, and SQL NULL guard cases. No test records were inserted into production.
- CRM API authorization/route tests passed; TypeScript checking passed.
- dsmonitor: all 115 tests passed.

The isolated database test demonstrated a complete **production-mode code path**, not a completed live business cycle. Live handoffs must still be established after rollout using actual IDs; dsmonitor must keep UNKNOWN where evidence is missing.

Exact sibling files and hashes: [change manifest](service-strategy-change-manifest.json). The dsmonitor change is `scripts/domain_daily.py` (review launcher and explicit input options), plus this report and the manifest. Original sibling files were backed up under `/tmp/service-strategy-upgrade/originals` before installation. Existing credentials, live records and cron schedules were left unchanged.

# Domain Merchant production cycle audit — 2026-09-26

Domain Merchant is **partially operational, not a complete production execution/feedback cycle**. Research persists successfully. Decision processing rejects the available candidates for missing evidence. Independently, the production execution gateway is not implemented in the inspected path: it only accepts test investigations, and CRM declares the adapter not ready.

Evidence was collected at 13:46 UTC (07:46 America/Denver), using existing authenticated CRM GET endpoints, local logs, receipt files and source inspection. See [the sanitized evidence](domain-merchant-cycle-audit.json). No business records were changed, workflow started, recommendation approved, paid provider called, email sent, engine restarted or purchase attempted.

## Trace through existing records

Organization: `06eaf14d-a535-4ccc-ad17-286da58d3fdd`.

| Step | Evidence | Conclusion |
| --- | --- | --- |
| MMonolith → CRM | Today's loans report `1e1035ea-e3f6-4993-83e6-8d474d58192c`, run key `2026-09-26-loans`, persisted at 13:00:08 UTC; matching real write receipt | Confirmed report persistence |
| CRM → Decision Engine | Existing decision logs show domain candidate evaluations; latest logged decision run `52bbb8eb-e37c-4dec-acf9-1cc724c8442b` completed with zero recommendations and no errors | Historical evaluation works; exact-ID consumption of today's report remains unproven. No Decision Engine receipt file existed at inspection |
| Decision Engine → CRM | Only recommendation is `1b25db61-8b70-4bf5-b8bd-d9e28bc6be01`, a September 20 generic `NO_ACTION` with no execution service or report reference | No actionable Domain Merchant recommendation; do not falsely link NO_ACTION to today's report |
| CRM → DevSpace One | Zero execution requests in organization context | No request exists to approve, claim or diagnose as late |
| DevSpace One → CRM | Zero execution results | No production execution demonstrated |
| CRM → MMonolith feedback | Zero predictions and feedback evaluations; learning logs return empty feedback IDs | No completed feedback loop |

CRM returned 28 reports (seven days × four subjects). Today's loans report has 50 candidates and 300 reported sales; mortgage, roofing and tools each have zero candidates and zero reported sales. Successful publication of an empty report does not establish useful research coverage.

The absence of today's decision receipts before its configured 08:00 daily job is not itself a failure. Historical decision logs lack enough explicit report lineage to prove an individual report handoff. Shared correlation IDs across report versions must not be treated as proof of a particular version's consumption.

## Immediate stopping point: missing research evidence

An **offline, non-persisting evaluation** of the fetched CRM context using the actual `DomainAcquisitionStrategy` reproduced:

- Selected report: `1e1035ea-e3f6-4993-83e6-8d474d58192c`.
- Eligible: false; score 25/100 against minimum 50.
- Confidence: 0.247525 against client minimum 0.65.
- All 50 candidates lack passing search-demand, buyer and acquisition-quote checks; 14 also fail comparable-sales coverage.
- The normal strategy correctly declines to recommend an unsupported action.

This evaluation did not call `DecisionService.run`, start a decision run, or publish a recommendation. It is diagnostic reproduction, not evidence that the live engine consumed this report.

`scripts/domain_daily.json` supplies no demand files, buyer files, availability files or enabled registrar checks. The launcher does not pass the optional billed keyword lookup flag. Thus missing evidence is expected with this configuration; an empty `provider_failures` list does not mean those sources were queried successfully.

The current policy requires at least three comparable sales, 100 monthly searches, one potential buyer, and an available quote no older than 24 hours. The quote must match GoDaddy/USD, declare `checkout_total`, and fit the $12 cap. The optional research provider is Namecheap and does not emit `price_type=checkout_total`. Merely enabling it cannot satisfy this contract. Neither changing registrar policy nor removing checks is an appropriate monitoring fix.

Sources: `mmonolith/services/domain_intelligence/discover.py`, `providers.py`; `decision_engine/decision_engine/strategies/domain_acquisition.py`, `config/scoring.json`; dsmonitor `scripts/domain_daily.py` and `.json`.

## Additional blockers beyond research

1. **Execution readiness:** CRM's Domain Merchant capability says `status=AVAILABLE` but `adapter_ready=false`, `allow_manual=false`. The request-creation SQL checks readiness and rejects an unavailable adapter. The AVAILABLE label alone does not authorize execution.
2. **Test-only worker:** `devspace-one/core/feedback_worker.py` requires `DEVSPACE_ENV=test`, a test report and test request, and only performs a dry-run investigation. `dsorchestrator/engines/bridge.py` explicitly rejects production execution through this gateway. Removing those guards would not implement a production worker.
3. **Scheduling:** the existing daily launcher runs research, decision and separate Afternic/Apollo jobs. It does not run the feedback request worker or coordinate one shared workflow ID. Existing outreach logs report no purchased/listed domains, no generated drafts, and no approved Apollo outreach. These are independent jobs, not proof of request-driven execution.
4. **Learning contract:** current raw-fact discovery deliberately publishes `predictions: []`. `mmonolith/services/domain_intelligence/service.py::learn` evaluates results against attributable predictions. With no predictions, this evaluator cannot produce feedback evaluations even if results later arrive. A supported outcome-learning contract is needed; invented predictions would be misleading. Separate outreach-performance ingestion exists but does not prove the requested result→evaluation chain.
5. **Authorization:** the organization has Domain Merchant enabled, approval required and `email_enabled=false`. There is currently no actionable recommendation awaiting approval. Purchases and outreach must remain subject to their explicit authorization rules.

## Required implementation/configuration sequence

1. Supply legitimate keyword-demand and potential-buyer evidence, and sales/candidate inputs for the other intended niches. Existing authorized exports can be used; paid API collection requires an explicit spending decision.
2. Implement or supply the configured registrar's complete, fresh quote contract. Preserve the cap and provenance; do not call a partial advertised price a checkout total.
3. Let a normal decision evaluate complete evidence. A legitimate NO_ACTION outcome remains acceptable; no candidate is guaranteed to qualify.
4. Implement and test a production **investigation** worker with explicit approval, tenant scope, claim/result idempotency and failure reporting. Its current action is investigation, not purchase. Register readiness only after that implementation is actually deployed and verified.
5. Connect the authorized request worker to the intended scheduler/orchestrator, preserving explicit report→recommendation→request→result IDs and workflow context.
6. Define evidence-backed predictions or an explicitly separate actual-outcome evaluation contract, then verify result→feedback→new-report lineage.
7. Deploy the already-written bounded CRM monitoring endpoint and configure truthful per-stage activity expectations. These improve monitoring but do not remove the business blockers above.

No runtime source or business configuration was changed during this audit: the checks are enforcing real requirements, and the missing production worker/research inputs require substantive implementation rather than a safe one-line repair. Deliverables are this report and its sanitized evidence JSON. Full raw CRM context was kept outside the repository in a private temporary file.

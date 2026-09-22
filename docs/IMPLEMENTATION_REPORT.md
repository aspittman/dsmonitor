# dsmonitor implementation report

Validation: 41 tests passed after the monitoring-access correction; desktop/mobile Chromium checks passed, including workflow filters, error context and HTML escaping. See [verification evidence](VERIFICATION.md).

1. **BotMonitor technology stack:** unavailable to verify. No local BotMonitor project was found in the searched directories. No assumption about its actual stack is presented as fact. dsmonitor uses Python 3.10+, Flask, SQLite, plain HTML/CSS/JavaScript, and optional psycopg for read-only PostgreSQL.

2. **BotMonitor reuse/adaptation:** no code or assets were copied because the source was unavailable. The requested monitoring patterns were implemented: restrained dark dashboard, overview metrics, engine/dependency status, activity/errors, detail panels, automatic refresh and local snapshot history. Direct visual/structural matching remains pending BotMonitor's path.

3. **Engine monitoring sources:** MMonolith's existing research SQLite database and logs; Decision Engine's captured JSON stdout if configured and CRM recommendations; DevSpace One's existing service logs and execution records; dsorchestrator's actual workflow/stage tables. All four also support local Python process observation, configured health endpoints, and configured heartbeat files. CRM and Supabase have independent API/database probes. See [discovery](DISCOVERY.md) for exact paths and contracts.

4. **Engine health:** explainable checks separate availability from health. A process only proves ONLINE. Explicit healthy API evidence plus dependency checks can establish HEALTHY. Failed dependencies or recent dated source failures produce DEGRADED; configured freshness thresholds can produce STALE. No process during an idle batch period is UNKNOWN. Undated historic traceback errors are visible but do not prove a current outage.

5. **CRM health:** authenticated read of the existing organization API; tenant context reads are separately checked when scoped. No dependency on the CRM frontend rendering. HTTP failure, access failure, invalid payload and network failure are distinguished in the card. Current deployed decision API returned HTTP 404.

6. **Supabase health:** independent PostgREST GET of `organizations?select=id&limit=1` using the configured/discovered anon key, or optional read-only PostgreSQL `SELECT 1`. A successful probe proves its connectivity/access, not all operational permissions. The latest probe returned HTTP 401 with PostgreSQL 42501 (permission denied), establishing database responsiveness but not read access. Supabase now shows ONLINE with a monitoring gap.

7. **CRM outage behavior:** its adapter returns an error status; engine process/log checks, local research, orchestrator state, independent database probe and monitoring history continue. CRM-dependent references remain unverifiable rather than fabricated.

8. **Supabase outage behavior:** independent sources still collect and render. The shared database error is identified on affected engine dependency panels. The configured orchestration backend is not silently switched to an unrelated local database. History is local and does not depend on Supabase.

9. **Process categories:** `domain`, `scholarship`, `devspace_services`, `crm_business`. Actual orchestrator aliases `devspace-services` and `crm-companies` are supported. Unknown workflow types also render. Scholarship remains NOT CONFIGURED because the inspected Schopath contract explicitly has no MMonolith/CRM integration.

10. **Workflow stages:** actual `stage_runs` rows, statuses, owners, attempts and timestamps. The inspected domain lifecycle has seven stages. Only explicit CRM records can add a recommendation lifecycle when no orchestrator run already tracks it. No generic measurement or dispatch stage is invented.

11. **Cross-engine lineage:** explicit output/input UUID references and existing same-organization CRM foreign keys. Record verification is labeled separately from source workflow assertions. No timestamp-nearness joins. Unknown or unavailable target records stay UNVERIFIED.

12. **Reliable metrics:** observed engine availability/degradation; complete-window orchestrator RUNNING, WAITING_FOR_APPROVAL, FAILED and completed-today counts; MMonolith stored observation/report UTC counts; source stage attempts, timestamps and durations; actual observed errors and source activity. All counts describe their source scope. Engine operation totals remain N/A unless a source can establish them.

13. **Unavailable metrics/evidence:** complete ecosystem operations/success/failure totals, total errors today, complete prospect/audit/draft/sent/response/backlog counts, live per-engine heartbeats, deployed decision/feedback context, scholarship workflow stages and real complete domain verification. No live run exists in the inspected local workflow database. No past monitor history is invented.

14. **Source improvements that would help:** dedicated side-effect-free engine health endpoints exposing dependency checks; UTC structured logs with event IDs, engine/run/organization IDs and safe error codes; worker heartbeats distinguishing job-idle from dead; a least-privilege monitoring credential; deploy the already implemented CRM read routes; paginated/projection-only monitoring context; append-only stage-transition/attempt history; structured outreach outcome ledgers; a deliberate scholarship integration. These are recommendations, not changes made by dsmonitor.

15. **Changes to existing projects:** none. No operational migrations, business logic changes, approvals, sends, workflow starts/retries or source CLI executions. Existing source SQLite was queried read-only; existing credentials were read server-side without copying them into new configuration files.

16. **Files created:** `app.py`, `config.py`, runtime/development/locked requirements, `.env.example`, `.gitignore`, `README.md`; adapters (`base`, `local`, `mmonolith`, `decision_engine`, `devspace_one`, `dsorchestrator`, `crm`, `supabase`); normalized models; process registry; services for collection, health, CRM processes, explicit lineage, security and snapshots; dashboard template/CSS/JS; pytest tests; safe verification/browser scripts; discovery/verification/report documentation and browser screenshots. Runtime uses `venv/` and `data/dsmonitor.db`. The latter is monitoring state only and ignored by version control.

17. **Start command:**

    ```bash
    cd /home/aaron/MyBotz/dsmonitor
    ./venv/bin/python app.py
    ```

18. **Local address:** http://127.0.0.1:5055. Binds to loopback only, with Host/client checks and GET-only dashboard APIs.

19. **Verify each engine:** run `./venv/bin/python scripts/verify_sources.py`, then compare the engine evidence panel with the exact source table/log/endpoint in [the verification guide](VERIFICATION.md). This command never executes an engine.

20. **Verify a complete workflow:** run `./venv/bin/python scripts/verify_sources.py --workflow EXISTING_WORKFLOW_UUID` after configuring its actual backend and explicit organization scope. Compare report → recommendation → approved request → result → feedback → updated report → new recommendation using the guide's foreign-key checklist. Current real source availability prevents a live complete verification; the historical synthetic trace and isolated schema fixture are not substitutes for it.

21. **Add a process:** use `register_process(id="google_play", display_name="Google Play", aliases=["google-play"])` or `DSMONITOR_EXTRA_PROCESSES`. Existing orchestrator rows with that type render without dashboard changes. Add a read-only adapter only if the new source format requires one. Registering a label does not claim the workflow is implemented.

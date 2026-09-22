# Current diagnosis — 2026-09-18, Mountain time

The all-DEGRADED display was not proof that four engines had failed. It propagated a missing CRM monitoring endpoint to every engine.

## Verified read-only evidence

| Check | Actual result | Meaning |
|---|---|---|
| Supabase Auth health | HTTP 200 | Auth endpoint responds |
| Supabase organizations SELECT | HTTP 401, PostgreSQL `42501`, permission denied for table organizations | Database responds, anonymous monitor role cannot read this table |
| CRM organizations monitoring API | HTTP 404 | Configured read route unavailable; check deployed CRM origin and API version |
| Local orchestrator database | Readable; zero runs | No local workflow outcome history to establish engine success |
| Local cron service | Active | Scheduler service is running, not proof any engine run succeeded |
| User cron | Three DevSpace One entries | Domain Merchant daily 08:00, Afternic sync 09:00, DevSpace Outreach 10:00, America/Denver |
| Other engine scheduling | No matching entries found | No MMonolith, Decision Engine or dsorchestrator jobs found in current-user crontab, inspected system cron files, or inspected system/user systemd configuration |

No account/project management action was taken. These probes establish database responsiveness, not the state of every Supabase subsystem or engine credential.

## Monitor correction

- HTTP error handling retains only HTTP status and a narrow database-code field, never the response body.
- PostgreSQL permission denial produces Supabase ONLINE plus a separate monitoring-read-access error. Engine database permissions remain UNKNOWN.
- CRM 401/403/404/405 and malformed monitoring responses show UNKNOWN with a monitoring-gap explanation. They do not mark all engines DEGRADED.
- Genuine unreachable dependencies and server errors still degrade affected engine health.
- UI banners keep the missing monitoring access visible.
- 41 tests pass, including permission-versus-outage classification and regressions for actual server failures.

Only dsmonitor files were changed. No credentials, grants, engine jobs, schedules or operational records were changed.

## Next operational work

1. Confirm the intended deployed/local CRM origin exposes the existing read-only decision-engine and feedback-loop APIs. Do not infer CRM health from its frontend alone.
2. Configure authorized, least-privilege monitoring reads. The anonymous role's lack of access is not a reason to expose organization data publicly.
3. Establish per-job last-start, completion status, completion time and stable run IDs from durable source records. Existing undated tracebacks cannot establish today's run outcome.
4. Configure the missing local engine schedules in their owning systems after choosing the intended cadence and reviewing their operational behavior. dsmonitor must only observe those schedules/results.
5. Add schedule-aware health: successful last due run → healthy/idle; failed attempt → error; missed expected run plus grace → overdue; no attributable outcome → unknown. Scheduling alone does not prove success.

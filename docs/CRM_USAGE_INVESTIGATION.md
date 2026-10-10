# CRM usage investigation — October 10, 2026

The owner identified DevSpace CRM as the Vercel project consuming the allowance. Reported Fluid Active CPU is 4h31m against 4h; the other supplied metrics are below their first displayed allowances. These are owner-reported account totals, not independently retrieved route measurements.

## Code-confirmed contributors and candidates

* `devspace-crm/lib/decision-engine-api.ts`: the authenticated context route loads complete tenant histories from eleven tables, the organization, and global execution capabilities. Each table uses SELECT * and repeats 500-row page reads until an empty page. With small nonempty tables this entails another empty-page request per table. The route assembles and serializes all records with no-store responses. Decision Engine's CRM client calls this context route; business schedules are independent of capability checks.
* `devspace-crm/lib/feedback-loop-api.ts`: the legacy context route loads complete histories from nine tables using the same page-until-empty pattern. MMonolith research and feedback learning still use it. The approved test investigation worker also calls it after claiming work. Previous periodic idle review/client workers were migrated to bounded work-context reads and their shared schedule remains paused pending live endpoint verification.
* Legacy instruction/action endpoints: Apollo's next-action route reads up to 500 lead records, 1,000 outreach records, and 1,000 sales records, with raw payloads included in several reads. Afternic's next-action route also has 1,000-row reads. These bounds cap row counts, not payload bytes. No current per-route call totals are available.
* Outreach performance reads up to 2,000 leads and 2,000 sales, including raw payloads, before computing its response. This consumes Supabase egress and Vercel processing even when the outgoing response contains only summarized information. The domain research client calls this route.
* Decision Engine GET retries allow three attempts for selected transient HTTP errors/network failures with short delays. This can amplify outages. Instrumented local launchers have shared provider backoff, but uninstrumented or remote clients do not inherit it automatically.
* Auth middleware calls Supabase getUser for matched page requests; API routes and selected assets are excluded. This is an additional request path, not evidence of a dominant source.

No recurring browser timer, subscription, EventSource, or refetch interval was found in the searched app/component TypeScript. This does not rule out external clients, crawlers, deployed versions, or dependency behavior.

## Attribution limits

The dominant retained Supabase gateway resources matched direct research capability probes. Those bypass Vercel and therefore cannot directly account for its CPU consumption. CRM-mediated full-history downloads are distinct candidates that consume both platforms. Source inspection establishes behavior, not each route's share of the reported 647K invocations, 68.89 GB CDN transfer, or CPU allowance. CDN transfer includes assets and cannot all be assigned to API responses from these totals.

No callable Vercel connector, installed Vercel CLI, local CLI credential store, or project-link directory was available in this environment. Exact ranking requires Vercel's function/request usage breakdown with project, route, time range, invocations, CPU and transfer. No large production context endpoint was called for this investigation.

## Recommended order

1. Keep redundant monitoring and idle worker schedules paused; capability checks are now every 30 minutes.
2. Verify the deployed bounded work-context endpoint before resuming review/client workers.
3. Replace business full-history downloads with explicitly scoped inputs, time windows and pagination/cursors. Preserve required decision/evidence history semantics: silently truncating the existing context contract could change decisions.
4. Move performance aggregation toward database-side summaries and select only needed fields; preserve current metric meanings.
5. Measure route/process counts and response sizes, then set budgets and longer idle/error backoff. Avoid per-request full payload logging or additional database writes for the meter.

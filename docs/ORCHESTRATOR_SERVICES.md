# DevSpace service orchestration

The local `devspace-services` and `crm-companies` workflows now coordinate MMonolith
research and service-specific Decision Engine advisory decisions. Research publications
and decisions carry the same organization, service and workflow identity. Their graphs
finish after decision; CRM approval and DevSpace One client draft preparation remain
separate. No new research schedule is installed.

Live read-only checks verified an enabled DevSpace Services organization and valid
research profiles for all six monitored client organizations. Existing Supabase and
search credentials are reused.

**Activation requirement:** set `SUPABASE_DB_URL` in
`/home/aaron/MyBotz/dsorchestrator/.env` to the PostgreSQL connection string for the
CRM Supabase project, including SSL configuration. The key currently has no value.
CRM validates workflow links against shared `workflow_runs`; SQLite-only run IDs
cannot be published. The local adapters and dsmonitor capability probe explicitly
report this missing setup. Keep `DEVSPACE_MODE=local` to run engines locally while
using shared PostgreSQL persistence. Hosted queue worker deployment is separate.

Use the existing dependencies through the launcher from dsmonitor:

```bash
venv/bin/python scripts/service_workflow.py run devspace-services --organization 2ee8ba95-35f4-4af9-b746-12071ed8815a --cycle 2026-W40 --dry-run
venv/bin/python scripts/service_workflow.py run crm-companies --organization 62539265-e1ae-4e14-8360-416747590585 --cycle 2026-W40 --dry-run
```

After database configuration, dry runs should report both stages available. Remove
`--dry-run` only for an intentional research/publication/advisory cycle. Research can
use the configured search provider. No live business cycle was executed during this
configuration work. Restart an existing dsmonitor process to load the updated registry
and capability probe. Registered participation does not imply verified healthy state.

## Schopath and Investorpath research routing

`scholarship_research` is the Schopath research/matching workload and
`investor_research` is the Investorpath research/matching workload. Both now use the
same local dsorchestrator bridge, shared PostgreSQL requirement, workflow identity
validation and scoped decision reads as the other service research workflows.
Dsmonitor registers dsorchestrator for both and reports missing shared persistence
as BLOCKED. Execution through DevSpace One and automatic scheduling remain disabled.

Read-only Supabase checks on 2026-10-03 verified both services enabled for the
DevSpace organization. Neither service has saved `matching_profiles`. Research can
run once persistence is configured; personalized matching also needs real student or
company attributes in the existing service's `config_json.matching_profiles`.
Profile IDs must be UUIDs. See MMonolith's `docs/product-research.md` for the existing
attribute and issuer-verification contracts. Discovery results without verified
issuer criteria remain research leads.

Optional `config_json.product_research` selects an absolute `source_export` path on
the MMonolith host, `issuer_domains` and a boolean `discover`. Default routing uses
the existing public discovery collector. It does not invent verified source facts.

```bash
venv/bin/python scripts/service_workflow.py run scholarship_research --organization 2ee8ba95-35f4-4af9-b746-12071ed8815a --cycle 2026-W40 --dry-run
venv/bin/python scripts/service_workflow.py run investor_research --organization 2ee8ba95-35f4-4af9-b746-12071ed8815a --cycle 2026-W40 --dry-run
```

App data transport remains separate: Schopath has its own Supabase schema and
Investorpath currently exposes an unconfigured backend repository interface.
Registering their research engines with dsorchestrator does not connect app login,
account-owned profiles, catalog reads or results displays. No app databases were
merged and no production research cycle was run during adapter configuration.

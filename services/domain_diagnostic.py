"""Evidence-based handoff assessment and bounded diagnostic report reads."""
import json
from pathlib import Path


def assess(report):
    checks = []
    def add(stage, status, owner, evidence, action):
        checks.append(dict(stage=stage, status=status, owner=owner, evidence=evidence, next_action=action))
    stages = report.get('stages', {})
    research = stages.get('research', {})
    decision = stages.get('decision', {})
    readiness = stages.get('readiness', {})
    for stage, owner in [('research', 'mmonolith'), ('decision', 'decision_engine'), ('readiness', 'devspace_one')]:
        result = stages.get(stage, {})
        if not result:
            add(stage, 'UNVERIFIED', owner, 'Stage has not completed.', 'Run or finish the diagnostic cycle.')
        elif not result.get('ok'):
            add(stage, 'FAILED', owner, result.get('error_type', 'Stage failed'),
                'Check engine configuration and connectivity; rerun after resolving the error.')
    r = research.get('result', {})
    d = decision.get('result', {})
    if research.get('ok'):
        add('research_output', 'VERIFIED' if r.get('candidate_count') else 'MISSING_INPUT', 'mmonolith',
            f"{r.get('candidate_count', 0)} candidates; {r.get('reported_sales', 0)} reported sales.",
            'Supply attributable comparable sales or explicit research seeds.' if not r.get('candidate_count') else 'Inspect downstream evidence checks.')
        for failure in r.get('provider_failures', []):
            add('provider_collection', 'FAILED', 'mmonolith', json.dumps(failure), 'Check this provider’s configuration and availability.')
        add('crm_report_readback', 'VERIFIED' if r.get('crm_readback') else 'UNVERIFIED', 'devspace-crm',
            'Report ID: ' + str(r.get('intelligence_report_id')),
            'Report was read back in the same organization.' if r.get('crm_readback') else 'Check report persistence and tenant-scoped context visibility.')
    if decision.get('ok'):
        linked = bool(r.get('intelligence_report_id')) and r['intelligence_report_id'] in d.get('consumed_report_ids', [])
        add('report_consumption', 'VERIFIED' if linked else 'UNVERIFIED', 'decision_engine',
            'Selected report IDs: ' + ', '.join(d.get('consumed_report_ids', [])),
            'Exact research report selected.' if linked else 'Check report selection, subject, organization, mode and concurrent newer reports.')
        add('decision_persistence', 'VERIFIED' if d.get('persisted') else 'UNVERIFIED', 'decision_engine / devspace-crm',
            'Decision run: ' + str(d.get('run_id')), 'CRM accepted the decision summary.' if d.get('persisted') else 'Check CRM decision persistence.')
        summary = d.get('summary', {})
        for error in summary.get('errors', []):
            add('strategy_execution', 'FAILED', 'decision_engine', json.dumps(error), 'Inspect the failing strategy and rerun.')
        candidates = summary.get('domain_candidate_decisions', [])
        requirements = {
            'comparable_sales': ('mmonolith', 'Import attributable, eligible comparable sales for these candidates.'),
            'search_demand': ('mmonolith inputs', 'Supply a current demand-file or explicitly enable the configured keyword provider.'),
            'potential_buyers': ('mmonolith inputs', 'Supply organization-scoped buyer observations using buyers_file.'),
            'available_with_affordable_quote': ('mmonolith inputs', 'Supply current attributable registrar checkout quotes using quote_file; verify the acquisition cap.'),
        }
        for requirement, (owner, action) in requirements.items():
            missing = sum(c.get('checks', {}).get(requirement) is False for c in candidates)
            if missing:
                add(requirement, 'MISSING_INPUT', owner,
                    f'{missing} of {len(candidates)} candidates failed this evidence check.', action)
        for strategy in summary.get('strategy_decisions', []):
            if strategy.get('service_id') != 'domain_merchant':
                continue
            for reason in strategy.get('blocking_reasons', []):
                adapter = 'adapter' in reason.lower()
                add(strategy['type'], 'CONFIGURATION_GAP' if adapter else 'POLICY_BLOCKED',
                    'devspace_one / CRM capability registration' if adapter else 'mmonolith inputs / Decision Engine policy', reason,
                    'Verify the review adapter implementation and allowed actions before registering it ready.' if adapter else
                    'Supply the cited evidence or review the organization’s policy; rerun evaluation without lowering gates to hide missing data.')
        caps = d.get('capabilities', [])
        ready = any(c.get('adapter_ready') is True and c.get('status') == 'AVAILABLE' and
                    'review_domain_evidence' in c.get('allowed_actions', []) for c in caps)
        add('review_adapter_registration', 'VERIFIED' if ready else 'CONFIGURATION_GAP', 'devspace_one / devspace-crm',
            'Review adapter is registered ready.' if ready else 'No available, ready review_domain_evidence capability.',
            'Registration is not execution proof; test an approved review separately.' if ready else 'Verify adapter implementation, status and allowed actions before updating registration.')
    if readiness.get('ok'):
        ready = readiness['result']
        reads = ready.get('reads', {})
        valid = ready.get('connectivity_status') == 'CONNECTED' and bool(reads) and all(v.get('status') == 'VERIFIED' for v in reads.values())
        oversized = any('4 MB' in v.get('reason', '') for v in reads.values())
        add('execution_read_access', 'VERIFIED' if valid else 'UNVERIFIED', 'devspace_one / CRM monitoring endpoint' if oversized else 'devspace_one',
            json.dumps({'connectivity': ready.get('connectivity_status'), 'reads': reads}),
            'Scoped reads succeeded; no request was claimed or executed.' if valid else
            'Deploy or repair the bounded CRM monitoring-capabilities endpoint; paginate large context responses instead of increasing the probe limit.' if oversized else
            'Check DevSpace One credentials, CRM reachability and required table access.')
    add('approved_execution', 'NOT_RUN', 'devspace_one', 'Diagnostic stops at readiness; no approvals, purchases or outreach.',
        'After resolving gaps, validate an explicitly approved zero-spend review separately.')
    gaps = [c for c in checks if c['status'] not in ('VERIFIED', 'NOT_RUN')]
    status = 'FAILED' if any(c['status'] == 'FAILED' for c in gaps) else 'BLOCKED' if gaps else 'READY_FOR_APPROVED_REVIEW'
    return {**report, 'status': status, 'checks': checks, 'gaps': gaps}


def recent_reports(directory, organizations, limit=20):
    reports = []
    for path in sorted(Path(directory).glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        try:
            if path.stat().st_size > 2_000_000:
                continue
            row = json.loads(path.read_text())
            if row.get('organization_id') in organizations:
                reports.append(row)
        except (OSError, ValueError):
            continue
        if len(reports) >= limit:
            break
    return reports

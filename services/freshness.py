"""Re-evaluate current readiness at read time; never re-date a cached observation."""
from collections import Counter
from copy import deepcopy
import time
from adapters.base import epoch, timestamp


def age_of(at, now):
    value = epoch(at)
    return max(0, now-value) if value is not None and value <= now else None


def freshness(at, ttl, now):
    age = age_of(at, now)
    return dict(status='UNKNOWN' if age is None else 'FRESH' if age <= ttl else 'STALE',
                checked_at=at, age_seconds=round(age, 1) if age is not None else None,
                expires_at=timestamp(epoch(at)+ttl) if epoch(at) is not None else None,
                max_age_seconds=ttl)


def readiness(report, organizations, ttl, now):
    clock = freshness(report.get('checked_at'), ttl, now)
    scope = bool(organizations) and set(organizations) <= set(report.get('organization_ids', []))
    result = dict(clock, owner='dsmonitor / engine probe', reason='No current engine-scoped verification.',
                  next_action='Check that automatic capability probes are completing for this organization.')
    if clock['status'] != 'FRESH':
        result['status'] = clock['status']
        if clock['status'] == 'STALE': result['reason'] = 'Capability verification expired; previous results are historical.'
        return result
    if not scope:
        result.update(status='UNKNOWN', reason='Probe does not cover all configured organizations.')
        return result
    connection = report.get('connectivity_status')
    reads = report.get('reads', {})
    config = report.get('configuration_status', 'UNVERIFIED')
    configurations=report.get('configuration_checks', [])
    disabled=bool(configurations) and all(c.get('verified') is True and c.get('service_enabled') is False for c in configurations)
    status = ('NOT_CONFIGURED' if disabled else 'DISCONNECTED' if connection == 'DISCONNECTED' else
              'BLOCKED' if config in ('MISSING', 'BLOCKED') else
              'DEGRADED' if connection == 'DEGRADED' or any(r.get('status') == 'FAILED' for r in reads.values()) else
              'UNKNOWN' if connection != 'CONNECTED' or not reads or any(r.get('status') != 'VERIFIED' for r in reads.values()) or config != 'VERIFIED' else 'READY')
    result.update(status=status, reason=report.get('reason') or 'Engine capability checks completed.',
                  next_action=report.get('next_action') or 'Inspect the required reads and configuration evidence.', owner='Engine configuration / CRM API')
    if status == 'READY':
        result.update(reason='Connectivity, required reads and configuration verified. Writes and business outcomes are separate.', next_action='No readiness repair indicated; inspect workflow outcomes separately.')
    elif status == 'NOT_CONFIGURED':
        result.update(reason='Service is disabled for the monitored organization scope.', next_action='No readiness repair required unless this service is intended to be enabled.')
    elif status == 'BLOCKED':
        result['reason'] = 'Required configuration is missing or blocked; see configuration evidence.'
    return result


def project(data, config, now=None):
    now = time.time() if now is None else now
    result = deepcopy(data)
    ttl = config.get('engine_capability_seconds', 90)
    snap = freshness(data.get('collected_at'), config.get('snapshot_max_age_seconds', 45), now)
    result['monitor_freshness'] = snap
    result['served_at'] = timestamp(now)
    result['probe_interval_seconds'] = config.get('probe_interval_seconds', 45)
    result['capability_max_age_seconds'] = ttl
    by_id = {e['engine_id']: e for e in result.get('engines', [])}
    matrix = result.get('trace_overview', {}).get('matrix', [])
    for cell in matrix:
        engine = by_id.get(cell['engine_id'], {})
        report = engine.get('service_capabilities', {}).get(cell['service_id'], {})
        scope = config.get('service_organization_ids', {}).get(cell['service_id'], config.get('organization_ids', []))
        current = readiness(report, scope, ttl, now)
        if cell.get('status') == 'NOT_CONFIGURED':
            current.update(status='NOT_CONFIGURED', reason=cell.get('reason'))
        if cell['engine_id'] == 'crm' and not report and current['status']!='NOT_CONFIGURED':
            # Legacy context access is historical; no bounded probe means unknown readiness.
            current.update(status='UNKNOWN', reason='CRM bounded capability verification is unavailable.', next_action='Check the CRM capability probe and endpoint.')
        if snap['status'] != 'FRESH' and current['status'] != 'NOT_CONFIGURED':
            current.update(status=snap['status'], reason='Monitor collection is stale or has not completed; live readiness is unverified.', next_action='Check dsmonitor collector health and logs.')
        cell['readiness'] = current
        observed_runs = [r for r in result.get('traces', []) if r.get('service_id')==cell['service_id'] and any(s.get('engine_id')==cell['engine_id'] and s.get('observed') for s in r.get('stages', []))]
        latest_run = max(observed_runs, key=lambda r: epoch(r.get('last_activity')) or 0, default={})
        cell['last_run_outcome'] = dict(status=latest_run.get('status', 'UNKNOWN'), last_success=cell.get('last_success'),
                                       last_activity=cell.get('last_activity'), trace_id=cell.get('latest_run'))
        cell['workflow_progress'] = dict(status=cell.get('handoff_status', 'UNKNOWN'), observed_at=data.get('collected_at'))
        # Preserve the old combined assessment only as an explicitly historical field.
        cell['combined_observation_status'] = cell.get('status')
        cell['status'] = cell['overall_status'] = current['status']
        cell['reason'] = current['reason']
        if current['status'] in ('STALE', 'UNKNOWN'):
            cell['connectivity_status'] = cell['read_status'] = 'UNKNOWN'
        if snap['status'] != 'FRESH':
            cell['workflow_progress']['status'] = 'STALE'
    for engine in result.get('engines', []):
        cells = [c for c in matrix if c['engine_id'] == engine['engine_id'] and c['readiness']['status'] != 'NOT_CONFIGURED']
        # Unattributed historical fragments do not define an engine capability contract.
        cells=[c for c in cells if c['service_id']!='unknown_service']
        checks = [c['readiness'] for c in cells]
        if not checks and engine.get('service_capabilities'):
            checks = [readiness(r, config.get('service_organization_ids', {}).get(service, config.get('organization_ids', [])), ttl, now) for service, r in engine['service_capabilities'].items()]
        if engine.get('infrastructure') and not engine.get('service_capabilities'):
            checks=[]
        if checks:
            order = ('DISCONNECTED', 'DEGRADED', 'BLOCKED', 'STALE', 'UNKNOWN', 'READY')
            current = deepcopy(min(checks, key=lambda r: order.index(r['status']) if r['status'] in order else 4))
        elif engine.get('infrastructure'):
            current = freshness(engine.get('observed_at'), max(ttl, config.get('capability_seconds',45)+config.get('refresh_seconds',10)), now)
            current.update(reason='Independent infrastructure probe; engine permissions are checked separately.', owner='Infrastructure configuration', next_action='Inspect the infrastructure probe evidence.')
            if current['status'] == 'FRESH':
                current['status'] = ('UNKNOWN' if engine['engine_id']=='crm' else 'READY') if engine.get('status') == 'HEALTHY' else engine.get('status', 'UNKNOWN')
                if engine.get('monitoring_issue'):
                    current.update(status='BLOCKED',reason=engine['monitoring_issue'],owner='dsmonitor infrastructure probe configuration',
                                   next_action='Repair the monitoring credential or read permission; engine access is checked separately through CRM.')
        else:
            current = dict(status='UNKNOWN', checked_at=None, expires_at=None, reason='No verified service capability checks.', owner='dsmonitor', next_action='Inspect the automatic probe results.')
        if snap['status'] != 'FRESH':
            current.update(status=snap['status'], reason='Monitor collection is stale or unavailable.', next_action='Check dsmonitor collector health and logs.')
        current['services']=[c['service_id'] for c in cells]
        if checks and current['status'] in ('UNKNOWN','STALE','BLOCKED','DEGRADED','DISCONNECTED'):
            affected=[c['service_id'] for c in cells if c['readiness']['status']==current['status']]
            if affected:current['reason']='; '.join(affected)+': '+current['reason']
        engine['readiness'] = current
        engine['historical_status'] = engine.get('status')
        engine['status'] = current['status']
        engine['last_run_outcome'] = dict(last_success=engine.get('last_success'), last_activity=engine.get('last_activity'),
                                          unresolved_failures=sum(c.get('workflow_status') == 'FAILED' for c in cells))
    if 'trace_overview' in result:
        result['trace_overview']['health_summary'] = dict(Counter(c['status'] for c in matrix))
    if snap['status'] != 'FRESH':
        if result.get('trace_overview',{}).get('summary'):
            for key in ('running','waiting','stalled'): result['trace_overview']['summary'][key]=None
        result.setdefault('monitor_errors', []).append('Live status expired. Historical outcomes retain their original timestamps.')
        for engine in result.get('engines', []): engine['availability'] = 'UNKNOWN'
        for key in ('engines_online', 'engines_degraded', 'active_processes', 'waiting_for_approval'):
            if key in result.get('summary', {}): result['summary'][key] = None
    return result

"""Bounded GET-only capability checks using each engine's configured credentials.

Never imports or starts a business engine. No fallback to unbounded context APIs.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.base import get_json, HTTPReadError, readonly_sqlite, readonly_postgres


def state_reads(org, env):
    dsn=env.get('SUPABASE_DB_URL')
    path=Path(env.get('ORCHESTRATOR_SQLITE_PATH','data/orchestrator.sqlite3'))
    context=readonly_postgres(dsn, 3) if dsn else readonly_sqlite(path)
    marker='%s' if dsn else '?'
    try:
        with context as db:
            db.execute('SELECT id FROM workflow_runs WHERE organization_id='+marker+' LIMIT 1',(org,)).fetchone()
            db.execute('SELECT s.id FROM stage_runs s JOIN workflow_runs w ON s.workflow_run_id=w.id WHERE w.organization_id='+marker+' LIMIT 1',(org,)).fetchone()
        return {t:{'status':'VERIFIED','reason':'Tenant-scoped read-only SELECT LIMIT 1 succeeded.'} for t in ('workflow_runs','stage_runs')}
    except Exception:
        return {t:{'status':'UNKNOWN','reason':'Orchestrator persistence read could not be verified; check its configured storage.'} for t in ('workflow_runs','stage_runs')}


def probe(profile, organizations, env=None, get=get_json):
    env = os.environ if env is None else env
    reports = {}
    service_scopes = json.loads(env.get('DEVSPACE_SERVICE_ORGANIZATIONS', '{}'))
    default_organizations = organizations
    for service, contract in profile['services'].items():
        organizations = [str(UUID(org)) for org in service_scopes[service]] if service in service_scopes else default_organizations
        if len(organizations) > 20: raise ValueError('At most 20 organizations per service')
        if profile['engine_id']=='mmonolith' and service in ('devspace_clients','devspace_services','scholarship_research','investor_research'):
            from scripts.client_direct_probe import probe_direct
            reports[service] = probe_direct(contract, organizations, env, get, service=service)
            continue
        checked = datetime.now(timezone.utc).isoformat()
        report = dict(checked_at=checked, organization_ids=organizations, connectivity_status='UNKNOWN',
            write_status='UNVERIFIED', configuration_scope=env.get('DEVSPACE_DIAGNOSTIC_SCOPE', 'engine environment'),
            reads={}, configuration_status='UNKNOWN', reason='No configured organization scope.', next_action='Configure the monitored organization IDs.')
        reports[service] = report
        url, secret = env.get(profile['url_env'], '').rstrip('/'), env.get(profile['secret_env'], '')
        if not organizations or not url or not secret:
            if not url or not secret:
                report.update(configuration_status='MISSING', reason='Engine CRM URL or credential is missing.',
                              next_action='Configure '+profile['url_env']+' and '+profile['secret_env']+' in the engine environment.')
            report['reads'] = {t: {'status': 'UNKNOWN', 'reason': report['reason']} for t in contract['inputs']}
            continue
        report['configuration_status'] = 'CONFIGURED'
        scoped = []
        for org in organizations:
            try:
                query = '?' + urlencode(dict(organization_id=org, engine_id=profile['engine_id'], service_id=service))
                envelope = get(url+'/api/bot/monitoring-capabilities', 5, {'Authorization': 'Bearer '+secret}, query)
                data = envelope['data']
                if envelope.get('success') is not True or any(data.get(k) != v for k, v in
                    [('organization_id', org), ('engine_id', profile['engine_id']), ('service_id', service)]):
                    raise ValueError('Invalid scope')
                reads = data.get('reads', {})
                if not isinstance(reads, dict): raise ValueError('Invalid reads')
                if profile['engine_id']=='dsorchestrator': reads.update(state_reads(org,env))
                scoped.append((data.get('connectivity_status', 'UNKNOWN'), reads, data.get('configuration', {}),
                               'Authenticated bounded CRM SELECT checks completed.', 'Inspect any failed table or configuration check.'))
            except HTTPReadError as exc:
                status = 'UNKNOWN' if exc.http_status in (400, 404, 405) else 'DEGRADED'
                reason = 'Monitoring endpoint missing or service contract unsupported (HTTP '+str(exc.http_status)+').' if status == 'UNKNOWN' else 'CRM read rejected: HTTP '+str(exc.http_status)+'.'
                action = 'Deploy the CRM monitoring-capabilities endpoint; historical context downloads are not used for readiness.' if status == 'UNKNOWN' else 'Check this engine’s CRM credential and required database access.'
                scoped.append((status, {}, {}, reason, action))
            except ConnectionError:
                scoped.append(('DISCONNECTED', {}, {}, 'CRM is unreachable or the read timed out.', 'Check CRM availability and engine network access.'))
            except Exception:
                scoped.append(('UNKNOWN', {}, {}, 'Invalid, oversized or incorrectly scoped monitoring response.', 'Repair the bounded CRM monitoring endpoint contract.'))
        rank = {'DISCONNECTED': 0, 'DEGRADED': 1, 'UNKNOWN': 2, 'CONNECTED': 3}
        worst = min(scoped, key=lambda r: rank.get(r[0], 2))
        report.update(connectivity_status=worst[0] if worst[0] in rank else 'UNKNOWN', reason=worst[3], next_action=worst[4])
        for table in contract['inputs']:
            rows = [r[1].get(table, {'status': 'UNKNOWN', 'reason': r[3]}) for r in scoped]
            report['reads'][table] = next((r for r in rows if r.get('status') == 'FAILED'), None) or next((r for r in rows if r.get('status') != 'VERIFIED'), None) or rows[0]
        configurations = [r[2] for r in scoped]
        report['configuration_checks'] = configurations
        if any(c.get('service_enabled') is False for c in configurations):
            report.update(configuration_status='BLOCKED', next_action='Review the organization service enablement in CRM.')
        elif any(c.get('adapter_ready') is False for c in configurations):
            report.update(configuration_status='BLOCKED', next_action='Verify the execution adapter implementation and allowed actions before registering readiness.')
        elif not all(c.get('verified') is True for c in configurations):
            report['configuration_status'] = 'UNVERIFIED'
        else:
            report['configuration_status'] = 'VERIFIED'
    return {'engine_id': profile['engine_id'], 'service_capabilities': reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--organization', action='append', default=[], type=lambda x: str(UUID(x)))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if len(args.organization)>20: parser.error('At most 20 organizations')
    profile = json.loads(Path(args.profile).read_text())
    result = probe(profile, args.organization)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        json.dump(result, f)
    temporary.replace(path)


if __name__ == '__main__': main()

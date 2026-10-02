"""Bounded GET-only checks for MMonolith's direct client Supabase connection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode
from adapters.base import get_json, HTTPReadError


def probe_direct(contract, organizations, env, get=get_json, service="devspace_clients"):
    if service not in ("devspace_clients","devspace_services","scholarship_research","investor_research"): raise ValueError("Unsupported direct service")
    checked = datetime.now(timezone.utc).isoformat()
    report = dict(checked_at=checked, organization_ids=organizations,
        connectivity_status='UNKNOWN', configuration_status='UNVERIFIED',
        configuration_scope='Direct research Supabase service-role environment',
        write_status='UNVERIFIED', reads={}, configuration_checks=[],
        reason='Direct Supabase connection has not been verified.',
        next_action='Check the client research Supabase configuration.')
    url, secret = env.get('CLIENT_SUPABASE_URL', '').rstrip('/'), env.get('CLIENT_SUPABASE_KEY', '')
    tables = contract['inputs']
    if not url or not secret or not organizations:
        report.update(configuration_status='MISSING', reason='Client Supabase credentials or organization scope missing.')
        report['reads'] = {t: {'status': 'UNKNOWN', 'reason': report['reason']} for t in tables}
        return report
    headers = {'apikey': secret, 'Authorization': 'Bearer ' + secret}
    def check(org):
        reads = {}
        try:
            query = '?' + urlencode({'organization_id': 'eq.' + org, 'service_key': 'eq.'+service,
                'is_enabled': 'eq.true', 'select': 'id,organization_id,is_enabled', 'limit': 1})
            profiles = get(url+'/rest/v1/organization_services', 5, headers, query)
            if not isinstance(profiles, list) or any(r.get('organization_id') != org for r in profiles):
                raise ValueError('Invalid profile scope')
            for table in tables:
                if table not in ('intelligence_reports', 'execution_results'):
                    raise ValueError('Unsupported direct monitoring table')
                filters = {'organization_id': 'eq.'+org, 'select': 'id,organization_id', 'limit': 1}
                filters['service_id' if table == 'intelligence_reports' else 'execution_service'] = 'eq.'+service
                rows = get(url+'/rest/v1/'+table, 5, headers, '?' + urlencode(filters))
                if not isinstance(rows, list) or any(r.get('organization_id') != org for r in rows):
                    raise ValueError('Invalid read scope')
                reads[table] = {'status': 'VERIFIED', 'reason': 'Direct tenant/service-scoped Supabase SELECT LIMIT 1 succeeded; empty rows are valid.'}
            return 'CONNECTED', reads, {'verified': True, 'service_enabled': bool(profiles)}, None
        except HTTPReadError as error:
            return 'DEGRADED', reads, {}, 'Direct Supabase read rejected: HTTP '+str(error.http_status)+'.'
        except ConnectionError:
            return 'DISCONNECTED', reads, {}, 'Direct Supabase connection timed out or is unreachable.'
        except Exception:
            return 'UNKNOWN', reads, {}, 'Invalid direct Supabase response or tenant scope.'
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check, organizations))
    ranking = {'DISCONNECTED': 0, 'DEGRADED': 1, 'UNKNOWN': 2, 'CONNECTED': 3}
    worst = min(results, key=lambda r: ranking[r[0]])
    report['connectivity_status'] = worst[0]
    report['configuration_checks'] = [r[2] for r in results]
    for table in tables:
        checks = [r[1].get(table, {'status': 'UNKNOWN', 'reason': r[3] or 'Not checked'}) for r in results]
        report['reads'][table] = next((r for r in checks if r['status'] != 'VERIFIED'), checks[0])
    report['reason'] = worst[3] or 'Direct Supabase profile and required reads verified; publication is checked through real persistence receipts.'
    if all(r[2].get('verified') is True and r[2].get('service_enabled') is True for r in results):
        report['configuration_status'] = 'VERIFIED'
        report['last_read'] = checked
        report['next_action'] = 'Inspect publication receipts and downstream CRM readiness separately.'
    elif any(r[2].get('service_enabled') is False for r in results):
        report['configuration_status'] = 'BLOCKED'
    return report

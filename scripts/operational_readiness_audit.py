"""Read-only rollout audit. Outputs statuses and configuration, never credentials."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.domain_deps'))
from dotenv import dotenv_values


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def main():
    crm = dotenv_values(ROOT.parent / 'devspace-crm/.env.local')
    one = dotenv_values(ROOT.parent / 'devspace-one/.env')
    scope = json.loads((ROOT / 'scripts/client_monitoring_scope.json').read_text())
    scope['domain_merchant'] = ['06eaf14d-a535-4ccc-ad17-286da58d3fdd']
    url = crm['NEXT_PUBLIC_SUPABASE_URL'].rstrip('/')
    key = crm['SUPABASE_SERVICE_ROLE_KEY']
    results = {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'configuration': {}}

    def get(base, path, headers):
        request = urllib.request.Request(base + path, headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
                return response.status, json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as error:
            return error.code, {}
        except (OSError, ValueError):
            return 'UNREACHABLE_OR_INVALID', {}

    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}
    for table, columns in {
        'workflow_runs': 'id,organization_id,service_id',
        'stage_runs': 'id,workflow_run_id',
        'intelligence_reports': 'id,organization_id,service_id,workflow_run_id',
        'feedback_evaluations': 'id,evaluation_kind',
        'service_registry': 'service_id,enabled',
    }.items():
        status, _ = get(url, '/rest/v1/' + table + '?select=' + columns + '&limit=1', headers)
        results['checks'].append({'check': table + ' schema access', 'http_status': status})
    status, capabilities = get(url, '/rest/v1/execution_capabilities?select=service_key,status,adapter_ready,allowed_actions', headers)
    results['execution_capabilities'] = capabilities if status == 200 else {'http_status': status}
    status, schema = get(url, '/rest/v1/', {**headers, 'Accept': 'application/openapi+json'})
    results['review_rpc_exposed'] = {
        name: '/rpc/' + name in schema.get('paths', {})
        for name in ('loop_claim_review', 'loop_observe_review')
    } if status == 200 else {'http_status': status}
    for service, orgs in scope.items():
        for org in orgs:
            status, rows = get(url, '/rest/v1/organization_services?' + urllib.parse.urlencode({
                'select': 'is_enabled,config_json', 'organization_id': 'eq.' + org,
                'service_key': 'eq.' + service, 'limit': 1,
            }), headers)
            config = rows[0].get('config_json') or {} if status == 200 and rows else {}
            results['checks'].append({'check': service + ' organization configuration', 'organization_id': org,
                'http_status': status, 'enabled': rows[0].get('is_enabled') if status == 200 and rows else None,
                'matching_profile_count': len(config.get('matching_profiles') or []) if status == 200 else None,
                'has_client_research': bool(config.get('client_research')) if status == 200 else None})
            for engine in ('dsorchestrator', 'devspace_one'):
                if engine == 'devspace_one' and service in ('scholarship_research', 'investor_research'):
                    continue
                status, response = get(one['CRM_BASE_URL'].rstrip('/'), '/api/bot/monitoring-capabilities?' + urllib.parse.urlencode({
                    'organization_id': org, 'service_id': service, 'engine_id': engine,
                }), {'Authorization': 'Bearer ' + one['CRM_BOT_API_SECRET']})
                results['checks'].append({'check': service + ' ' + engine + ' deployed capability route',
                    'organization_id': org, 'http_status': status,
                    'reads': {k: v.get('status') for k,v in response.get('data', {}).get('reads', {}).items()},
                    'configuration': response.get('data', {}).get('configuration', {})})
    orchestrator = dotenv_values(ROOT.parent / 'dsorchestrator/.env')
    results['configuration']['shared_postgres_configured'] = bool(orchestrator.get('SUPABASE_DB_URL'))
    target = ROOT / 'docs/operational-readiness-audit.json'
    target.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()

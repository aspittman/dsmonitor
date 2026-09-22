import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import UUID
from adapters.base import get_json
from models import EngineStatus


def collect(config, cache=None):
    if cache is None: cache = {}
    engine = EngineStatus('crm', 'DevSpace CRM', infrastructure=True).dict()
    contexts, organizations = {}, []
    if not config['crm_url'] or not config['crm_token']:
        engine['checks'] = [{'name':'CRM API','status':'UNKNOWN','reason':'CRM URL or API credential not configured'}]
        return engine, contexts, organizations
    headers = {'Authorization':'Bearer ' + config['crm_token']}
    def get(route, org=None):
        result = get_json(config['crm_url'].rstrip('/')+route, config['timeout_seconds'], headers,
                          '?' + urlencode({'organization_id':org}) if org else '')
        if not isinstance(result, dict) or result.get('success') is not True: raise ValueError('Invalid CRM envelope')
        return result['data']
    try:
        orgs = get('/api/decision-engine/organizations')
        if not isinstance(orgs, list): raise ValueError('Invalid organizations')
        engine['status'] = 'HEALTHY'
        engine['checks'] = [{'name':'CRM API','status':'HEALTHY','reason':'Authenticated read of organization API succeeded; frontend is not required'}]
        for org in orgs:
            oid = str(UUID(org['id']))
            if oid not in config['organization_ids']: continue
            organizations.append({'id':oid,'name':org.get('name') or oid})
            try:
                cached = cache.get(oid)
                if cached and time.monotonic() - cached[0] < config['crm_context_seconds']:
                    contexts[oid] = cached[1]
                    continue
                context = get('/api/decision-engine/context', oid)
                context.update(get('/api/bot/feedback-loop/context', oid))
                for table, rows in context.items():
                    if table == 'execution_capabilities': continue
                    key = 'id' if table == 'organizations' else 'organization_id'
                    if not isinstance(rows, list) or any(r.get(key) != oid for r in rows): raise ValueError('Tenant mismatch')
                context['_observed_at'] = datetime.now(timezone.utc).isoformat()
                contexts[oid] = context
                cache[oid] = (time.monotonic(), context)
            except Exception:
                engine['status'] = 'DEGRADED'
                engine['dependency_status'] = 'UNKNOWN'
                engine['monitoring_issue'] = 'Organization monitoring context could not be verified; this does not establish an engine failure'
                engine['checks'].append({'name':'Organization '+oid,'status':'UNKNOWN','reason':'Context unavailable, oversized, or tenant validation failed'})
        if contexts:
            oldest = min(ctx['_observed_at'] for ctx in contexts.values())
            engine['checks'].append({'name':'CRM context freshness','status':'ONLINE','reason':f'Oldest context observation: {oldest}; refresh interval {config["crm_context_seconds"]}s'})
        if not config['organization_ids']:
            engine['checks'].append({'name':'Business scope','status':'UNKNOWN','reason':'Configure organization_ids to enable tenant-scoped CRM traces'})
    except ConnectionError as exc:
        engine['status'] = 'ERROR' if str(exc).startswith('HTTP ') else 'OFFLINE'
        engine['checks'] = [{'name':'CRM API','status':engine['status'],'reason':str(exc)}]
        if str(exc) in ('HTTP 401','HTTP 403','HTTP 404','HTTP 405'):
            engine['status'] = 'UNKNOWN'
            engine['dependency_status'] = 'UNKNOWN'
            reason = ('The configured CRM monitoring route is unavailable; verify the deployed CRM URL and read API'
                      if str(exc) in ('HTTP 404','HTTP 405') else 'The CRM monitoring credential lacks access')
            engine['monitoring_issue'] = str(exc) + ' — ' + reason
            engine['checks'][0]['reason'] = engine['monitoring_issue']
    except Exception:
        engine['status'] = 'UNKNOWN'
        engine['dependency_status'] = 'UNKNOWN'
        engine['monitoring_issue'] = 'CRM monitoring response/configuration is invalid; operational health is unverified'
        engine['checks'] = [{'name':'CRM API','status':'ERROR','reason':'Invalid API response or endpoint configuration'}]
    return engine, contexts, organizations

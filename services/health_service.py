from datetime import datetime, timezone
from adapters.base import epoch

DEPENDENCIES = {'mmonolith':['crm','supabase'],'decision_engine':['crm','supabase'],
                'devspace_one':['crm','supabase'],'dsorchestrator':['crm','supabase']}


def explain(engines, processes):
    by_id = {e['engine_id']:e for e in engines}
    now = datetime.now(timezone.utc).timestamp()
    for engine in engines:
        online = any(c['name'] in ('Local process','Heartbeat','API') and c['status'] in ('ONLINE','HEALTHY') for c in engine['checks'])
        engine['availability'] = 'ONLINE' if online else 'OFFLINE' if any(c['name']=='API' and c['status']=='OFFLINE' for c in engine['checks']) else 'UNKNOWN'
        if engine['infrastructure']:
            engine['availability'] = 'ONLINE' if engine['status'] in ('HEALTHY','ONLINE') else 'UNKNOWN'
            continue
        for dep in DEPENDENCIES.get(engine['engine_id'], []):
            status = by_id[dep].get('dependency_status') or by_id[dep]['status']
            engine['dependencies'].append({'name':by_id[dep]['display_name'],'status':status,'engine_id':dep,'probe_status':by_id[dep]['status'],'reason':by_id[dep].get('monitoring_issue') or ('Monitor access does not establish engine dependency health' if status != by_id[dep]['status'] else None)})
        owned = [(p,s) for p in processes for s in p['stages'] if s['engine'] == engine['engine_id']]
        active = [s['stage'] for p,s in owned if s['status']=='RUNNING' and p['status'] not in ('CANCELLED','COMPLETED','FAILED')]
        activity_times = [s['completed_at'] or s['started_at'] for p,s in owned if s['completed_at'] or s['started_at']]
        if activity_times: engine['last_activity'] = max(activity_times + ([engine['last_activity']] if engine['last_activity'] else []))
        failed = sorted([s for p,s in owned if s['error']], key=lambda s:s['completed_at'] or s['started_at'] or '', reverse=True)
        if failed: engine['last_error'] = failed[0]['error']
        engine['current_operation'] = ', '.join(sorted(set(active))) or None
        successful = [s['completed_at'] for p,s in owned if s['status']=='COMPLETED' and s['completed_at']]
        if successful: engine['last_success'] = max(successful + ([engine['last_success']] if engine['last_success'] else []))
        recent_errors = [a for a in engine['errors'] if epoch(a['timestamp']) and 0 <= now-epoch(a['timestamp']) < 3600]
        failures = [s for p,s in owned if s['status']=='FAILED' and s['completed_at'] and 0 <= now-epoch(s['completed_at']) < 3600]
        dependency_failure = any(d['status'] in ('OFFLINE','ERROR','DEGRADED') for d in engine['dependencies'])
        if dependency_failure:
            failed_names = ', '.join(d['name'] for d in engine['dependencies'] if d['status'] in ('OFFLINE','ERROR','DEGRADED'))
            engine['checks'].append({'name':'Dependencies','status':'DEGRADED','reason':failed_names + ' failed its dependency probe; local availability is evaluated separately'})
            if engine['status'] not in ('OFFLINE','ERROR'): engine['status']='DEGRADED'
        elif any(d['status']=='UNKNOWN' for d in engine['dependencies']):
            names = ', '.join(d['name'] for d in engine['dependencies'] if d['status']=='UNKNOWN')
            engine['checks'].append({'name':'Monitoring coverage','status':'UNKNOWN','reason':names + ' monitoring access is incomplete; this does not establish an engine failure'})
        if recent_errors or failures:
            engine['checks'].append({'name':'Recent failures','status':'DEGRADED','reason':'Failures observed during the last hour; bounded evidence, not a calculated failure rate'})
            if engine['status'] not in ('OFFLINE','ERROR'): engine['status']='DEGRADED'
        if engine['status']=='HEALTHY' and any(d['status']=='UNKNOWN' for d in engine['dependencies']):
            engine['status']='ONLINE'
            engine['checks'].append({'name':'Coverage','status':'UNKNOWN','reason':'API healthy but dependency coverage is incomplete'})
        undated = sum(not a.get('timestamp') for a in engine['errors'])
        if undated:
            engine['checks'].append({'name':'Undated log errors','status':'UNKNOWN','reason':f'{undated} error entries observed; age is unknown, so they do not establish current health'})
        if not any(c['name']=='API' for c in engine['checks']):
            engine['checks'].append({'name':'Health coverage','status':'UNKNOWN','reason':'No health endpoint configured. Stored activity does not prove current health'})
    return engines

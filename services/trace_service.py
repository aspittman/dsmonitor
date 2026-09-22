"""Evidence-based trace projections. Never infer lineage from time or service names."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from adapters.base import epoch, timestamp
from service_registry import ENGINES, identify, registry

STATUSES = {'NOT_STARTED', 'RUNNING', 'COMPLETED', 'WAITING', 'WAITING_FOR_APPROVAL',
            'STALLED', 'FAILED', 'SKIPPED', 'CANCELLED', 'UNKNOWN'}
ALIASES = {'PENDING': 'NOT_STARTED', 'STALE': 'STALLED', 'SUCCESS': 'COMPLETED',
           'SUCCEEDED': 'COMPLETED', 'ERROR': 'FAILED', 'APPROVED': 'WAITING',
           'RECOMMENDED': 'WAITING_FOR_APPROVAL', 'IN_PROGRESS': 'RUNNING'}


def status(value):
    value = str(value or '').upper()
    return value if value in STATUSES else ALIASES.get(value, 'UNKNOWN')


def key(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:32]


def normalize(processes, config):
    definitions = registry(config)
    runs, events = [], []
    for p in processes:
        service = identify(p['process_type'], definitions)
        # Orchestrator ID is authoritative. A CRM recommendation is an explicitly
        # linked fragment, never an invented end-to-end workflow ID.
        reliable = p.get('source') == 'dsorchestrator'
        rid = key('workflow' if reliable else p.get('source'), p.get('organization_id'), p['process_id'])
        run = {'trace_id': rid, 'workflow_run_id': p['process_id'] if reliable else None,
               'source_run_id': p['process_id'], 'source': p.get('source'),
               'service_id': service, 'organization_id': p.get('organization_id'),
               'parent_run_id': p.get('parent_run_id'), 'correlation_id': p.get('correlation_id'),
               'correlation_quality': 'AUTHORITATIVE RUN' if reliable else 'LEGACY / UNCORRELATED',
               'started_at': timestamp(p.get('started_at')), 'completed_at': timestamp(p.get('completed_at')),
               'last_activity': timestamp(p.get('last_activity')), 'source_status': status(p['status'] if p['status'] in ('SKIPPED','WAITING_FOR_APPROVAL') else p.get('source_status') or p['status']),
               'source_current_stage': p.get('current_stage'), 'error_message': p.get('last_error'),
               'lineage': p.get('lineage', []), 'expected_path': reliable,
               'reason': p.get('reason'), 'observed_at': datetime.now(timezone.utc).isoformat()}
        runs.append(run)
        for s in p['stages']:
            attempt = s.get('attempt') or (s.get('retries') or 0) + 1
            common = {'trace_id': rid, 'workflow_run_id': run['workflow_run_id'],
                      'parent_run_id': run['parent_run_id'], 'service_id': service,
                      'organization_id': run['organization_id'], 'correlation_id': run['correlation_id'],
                      'engine_id': s['engine'], 'stage': s['stage'], 'attempt': attempt,
                      'source_reference': s.get('source_reference') or p['process_id'] + ':' + s['stage'],
                      'metadata': {'references': s.get('references', {})}, 'error_type': None}
            if s.get('started_at'):
                events.append(dict(common, trace_event_id=key(rid,s['engine'],s['stage'],attempt,'started'),
                    event_type='stage_started', status='RUNNING', timestamp=s['started_at'],
                    duration_ms=None, message='Stage started', error_message=None))
            at = s.get('completed_at') or s.get('started_at') or p.get('last_activity')
            st = status(s['status'])
            events.append(dict(common, trace_event_id=key(rid,s['engine'],s['stage'],attempt,'state',st,at),
                event_type='stage_state_observed', status=st, timestamp=at,
                duration_ms=s['duration_seconds']*1000 if s.get('duration_seconds') is not None else None,
                message=s.get('error') or 'Source stage status: ' + str(s['status']), error_message=s.get('error'),
                time_quality='source stage' if s.get('completed_at') or s.get('started_at') else 'workflow observation'))
    return runs, events


def project(run, events, config, now=None):
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    definitions = registry(config)
    spec = definitions.get(run['service_id'], {})
    path = spec.get('stages', []) if run.get('expected_path') else []
    grouped = defaultdict(list)
    for event in events:
        grouped[(event['engine_id'], event['stage'])].append(event)
    order = [(s['engine_id'], s['stage']) for s in path]
    order += [pair for pair in grouped if pair not in order]
    stages = []
    for engine, name in order:
        rows = sorted(grouped[(engine, name)], key=lambda e: (e.get('attempt', 1), epoch(e.get('timestamp')) or 0, e['event_type'] != 'stage_started'))
        latest = rows[-1] if rows else None
        st = latest['status'] if latest else 'NOT_STARTED'
        last = latest.get('timestamp') if latest else None
        stage_spec = next((s for s in path if s['stage']==name and s['engine_id']==engine), {})
        threshold = config.get('trace_thresholds', {}).get(run['service_id'], {}).get(engine, {}).get(name, {})
        threshold = {**stage_spec, **threshold}
        stall = threshold.get('stalled_seconds')
        # Approval waiting never ages into a business failure. Other waits require
        # explicit opt-in because idle time alone is not evidence of a stall.
        elapsed = max(0, now-epoch(last)) if epoch(last) is not None else None
        if stall and elapsed is not None and elapsed > stall and (st=='RUNNING' or st=='WAITING' and threshold.get('stall_waiting')):
            st = 'STALLED'
        attempts = {}
        for row in rows:
            attempts[row.get('attempt',1)] = row
        durations = [r['duration_ms']/1000 for r in attempts.values() if r.get('duration_ms') is not None and r.get('time_quality') != 'workflow observation']
        start_times = [epoch(e['timestamp']) for e in rows if e['event_type']=='stage_started' and e.get('attempt',1)==(latest or {}).get('attempt',1)]
        stages.append({'engine_id':engine, 'stage':name, 'status':st, 'observed':bool(rows),
            'last_activity':last, 'elapsed_seconds':elapsed,
            'time_in_stage_seconds':max(0,now-min(start_times)) if start_times and st in ('RUNNING','STALLED','WAITING','WAITING_FOR_APPROVAL') else None,
            'expected_seconds':threshold.get('expected_seconds'), 'stalled_seconds':stall,
            'duration_seconds':sum(durations) if durations else None,
            'attempts':[{'attempt':a, 'status':r['status'], 'error_message':r.get('error_message'), 'timestamp':r.get('timestamp')} for a,r in sorted(attempts.items())],
            'completed_after_retry':st=='COMPLETED' and any(r['status']=='FAILED' for a,r in attempts.items()),
            'error_message':latest.get('error_message') if latest else None})
    failed = next((s for s in stages if s['status']=='FAILED'), None)
    active = next((s for s in stages if s['status'] in ('STALLED','WAITING_FOR_APPROVAL','RUNNING','WAITING')), None)
    source_status = run['source_status']
    if not active and source_status in ('RUNNING','WAITING','WAITING_FOR_APPROVAL','STALLED') and run.get('source_current_stage'):
        name=run['source_current_stage']
        owner=next((s['engine_id'] for s in stages if s['stage']==name), 'crm' if name=='approval' else 'UNKNOWN')
        active={'engine_id':owner,'stage':name,'status':source_status,'time_in_stage_seconds':None}
    root = failed
    if source_status=='FAILED' and not failed:
        root = {'engine_id':'dsorchestrator' if run.get('source')=='dsorchestrator' else 'UNKNOWN',
                'stage':run.get('source_current_stage') or 'coordination', 'error_message':run.get('error_message')}
    if root:
        result_status = 'FAILED'
    elif source_status in ('COMPLETED','CANCELLED'):
        result_status = source_status
    elif active:
        result_status = active['status']
    else:
        result_status = source_status
    # Only a verified sequential expectation can establish downstream non-reach.
    cutoff = stages.index(failed) if failed else next((i-1 for i,s in enumerate(stages) if s['stage']==run.get('source_current_stage')),len(stages))
    downstream = []
    for i, stage in enumerate(stages):
        if not stage['observed'] or stage['status']=='NOT_STARTED':
            if root and run.get('expected_path') and (i>cutoff):
                stage['status']='NOT_REACHED'
                downstream.append(stage)
    successes = [s for s in stages[:cutoff] if s['status']=='COMPLETED'] if failed else [s for s in stages if s['status']=='COMPLETED']
    start,end = epoch(run.get('started_at')),epoch(run.get('completed_at'))
    durations = [s['duration_seconds'] for s in stages if s['duration_seconds'] is not None and s['stage']!='approval' and s['status'] not in ('WAITING','WAITING_FOR_APPROVAL')]
    engine_timings=[]
    for engine in dict.fromkeys(s['engine_id'] for s in stages):
        execution=[s['duration_seconds'] for s in stages if s['engine_id']==engine and s['stage']!='approval' and s['duration_seconds'] is not None and s['status'] not in ('WAITING','WAITING_FOR_APPROVAL')]
        approval=[s['duration_seconds'] for s in stages if s['engine_id']==engine and s['stage']=='approval' and s['duration_seconds'] is not None]
        engine_timings.append({'engine_id':engine,'observed_execution_seconds':sum(execution) if execution else None,'observed_approval_seconds':sum(approval) if approval else None})
    return {**run, 'engine_timings':engine_timings, 'status':result_status, 'stages':stages, 'events':sorted(events,key=lambda e:epoch(e.get('timestamp')) or 0),
            'root_failure':root, 'cut_off_at':root['engine_id'] if root else None,
            'last_successful_stage':successes[-1] if successes else None,
            'downstream_not_reached':[{'engine_id':s['engine_id'],'stage':s['stage']} for s in downstream],
            'current':active if result_status not in ('FAILED','COMPLETED','CANCELLED') else root,
            'duration_seconds':max(0,end-start) if start is not None and end is not None else None,
            'elapsed_seconds':max(0,now-start) if start is not None else None,
            'observed_execution_seconds':sum(durations) if durations else None,
            'timing_note':'Observed attempt durations only; approval excluded. Missing intervals and human wait are not estimated.'}


def overview(runs, config, engines=(), now=None):
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    today = datetime.fromtimestamp(now,timezone.utc).date().isoformat()
    definitions = registry(config)
    services = sorted(set(definitions) | {r['service_id'] for r in runs})
    cells = []
    for service in services:
        spec = definitions.get(service, {})
        for engine in ENGINES:
            observations = []
            for run in runs:
                if run['service_id']!=service: continue
                stages = [s for s in run['stages'] if s['engine_id']==engine and s['observed']]
                if stages:
                    # Multiple stages in the same engine: any current failure wins.
                    selected = next((s for s in stages if s['status']=='FAILED'),None) or next((s for s in stages if s['status']=='STALLED'),None) or max(stages,key=lambda s:epoch(s['last_activity']) or 0)
                    observations.append((run, selected))
                elif run.get('root_failure',{} ) and run['root_failure']['engine_id']==engine:
                    observations.append((run, {'status':'FAILED','last_activity':run['last_activity'],'duration_seconds':None}))
            observations.sort(key=lambda pair:epoch(pair[1]['last_activity']) or 0,reverse=True)
            configured = any(s['engine_id']==engine for s in spec.get('stages',[])) or spec.get('coordinator')==engine
            st = observations[0][1]['status'] if observations else 'NO_DATA' if configured else 'NOT_CONFIGURED'
            successes = [s['last_activity'] for r in runs if r['service_id']==service for s in r['stages'] if s['engine_id']==engine and s['status']=='COMPLETED' and s.get('last_activity')]
            failed_attempts = sum(e['status']=='FAILED' and (e.get('timestamp') or '').startswith(today) for r in runs if r['service_id']==service for e in r['events'] if e['engine_id']==engine)
            consecutive = 0
            for _, observed in observations:
                if observed['status']!='FAILED': break
                consecutive += 1
            fails = sum(s['status']=='FAILED' and (s.get('last_activity') or '').startswith(today) for r,s in observations)
            reason = 'Latest observed run in this engine; bounded monitoring evidence.'
            if st=='COMPLETED':
                st='HEALTHY' if observations[0][1].get('last_activity') else 'UNKNOWN'
                if st=='UNKNOWN': reason='Completion observed in an undated source; current service health is unknown.'
            if any(s['status']=='STALLED' for _,s in observations):
                st='STALLED'; reason='At least one observed run exceeded an explicitly configured activity threshold.'
            elif consecutive:
                reason=f'{consecutive} consecutive observed run(s) failed inside this engine.'
            frequency = spec.get('expected_activity_seconds')
            if observations and frequency and now-(epoch(observations[0][1]['last_activity']) or now)>frequency:
                st='DEGRADED'; reason='Configured expected activity interval exceeded; not a workflow failure.'
            if not observations:
                blocked = [r for r in runs if r['service_id']==service and any(s['engine_id']==engine for s in r['downstream_not_reached'])]
                latest_run = max((r for r in runs if r['service_id']==service),key=lambda r:epoch(r.get('last_activity')) or 0,default=None)
                if latest_run in blocked and latest_run is not None: st='NOT_REACHED'; reason='Latest workflow stopped upstream; this engine is not counted as failed.'
                else: reason='Configured path has no observed stage records.' if configured else spec.get('note','No registered path or observed records.')
            available = next((e.get('availability') for e in engines if e['engine_id']==engine), 'UNKNOWN')
            cells.append({'service_id':service,'engine_id':engine,'status':st,'reason':reason,
                'availability':available,'last_success':max(successes) if successes else None,
                'last_activity':observations[0][1]['last_activity'] if observations else None,
                'latest_run':observations[0][0]['trace_id'] if observations else None,
                'failures_today':fails,'failed_attempts_today':failed_attempts,'consecutive_failures':consecutive,'observed_runs':len(observations),
                'average_duration_seconds':(sum(s['duration_seconds'] for r,s in observations if s.get('duration_seconds') is not None)/sum(s.get('duration_seconds') is not None for r,s in observations)) if any(s.get('duration_seconds') is not None for r,s in observations) else None})
    # Only authoritative runs enter workflow totals, not overlapping CRM fragments.
    reliable = [r for r in runs if r.get('workflow_run_id')]
    counts = Counter(r['status'] for r in reliable)
    failures = [r for r in reliable if r['root_failure']]
    def common(field):
        values = Counter((r['service_id'] if field=='service_id' else r['root_failure'][field]) for r in failures)
        return values.most_common(1)[0][0] if values else None
    stalled = sorted((r for r in reliable if r['status']=='STALLED'),key=lambda r:r.get('last_activity') or '')
    failures.sort(key=lambda r:r.get('last_activity') or '',reverse=True)
    return {'matrix':cells,'services':[{'service_id':s,**definitions.get(s,{'note':'Unregistered service; actual events retained.'})} for s in services],
        'summary':{'completed_today':sum(r['status']=='COMPLETED' and (r.get('completed_at') or '').startswith(today) for r in reliable),
            'running':counts['RUNNING'],'waiting':counts['WAITING']+counts['WAITING_FOR_APPROVAL'],
            'stalled':counts['STALLED'],'failed':counts['FAILED'], 'observed_runs':len(reliable),
            'most_common_failing_service':common('service_id'),'most_common_failing_engine':common('engine_id'),
            'most_common_failing_stage':common('stage'),'oldest_stalled':stalled[0]['trace_id'] if stalled else None,
            'most_recent_failure':failures[0]['trace_id'] if failures else None,
            'scope':'Observed authoritative workflows retained locally; not ecosystem-wide totals. UTC days.'}}

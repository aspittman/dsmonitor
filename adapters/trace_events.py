"""Optional bounded structured JSONL source; each configured engine fails independently."""
import json
from pathlib import Path
from adapters.base import timestamp
from services.trace_service import key, status


def collect(config):
    runs, events, issues = {}, [], []
    for engine, filename in config.get('trace_files', {}).items():
        try:
            with Path(filename).open('rb') as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size-2_000_000))
                if size>2_000_000: stream.readline()
                lines = stream.readlines()[-2000:]
            for line in lines:
                try:
                    row = json.loads(line)
                    if row.get('engine_id') != engine: raise ValueError('Engine mismatch')
                    workflow = row.get('workflow_run_id')
                    if not workflow or not row.get('service_id') or not row.get('stage'): raise ValueError('Missing context')
                    org = row.get('organization_id')
                    if org and org not in config.get('organization_ids', []): continue
                    at = timestamp(row.get('timestamp'))
                    if not at: raise ValueError('Missing time')
                    rid = key('workflow',org,workflow)
                    allowed = ('workflow_run_id','parent_run_id','service_id','organization_id','correlation_id',
                               'engine_id','stage','event_type','message','error_type','error_message','source_reference')
                    event = {k:row.get(k) for k in allowed}
                    event.update(trace_id=rid,trace_event_id=key(rid,engine,row.get('trace_event_id') or [row['stage'],at,row.get('event_type'),row.get('attempt',1)]),
                                 status=status(row.get('status')), timestamp=at, attempt=max(1,int(row.get('attempt',1))),
                                 duration_ms=max(0,float(row['duration_ms'])) if row.get('duration_ms') is not None else None,
                                 metadata={k:row.get('metadata', {}).get(k) for k in ('table','record_id')
                                           if isinstance(row.get('metadata'), dict) and isinstance(row['metadata'].get(k), str)},time_quality='source event')
                    if rid in runs and runs[rid]['service_id']!=row['service_id']: raise ValueError('Inconsistent service')
                    events.append(event)
                    run = runs.setdefault(rid,dict(trace_id=rid,workflow_run_id=workflow,source_run_id=workflow,
                        source='structured_trace',service_id=row['service_id'],organization_id=org,
                        parent_run_id=row.get('parent_run_id'),correlation_id=row.get('correlation_id'),
                        correlation_quality='EXPLICIT TRACE CONTEXT',started_at=None,completed_at=None,last_activity=at,
                        source_status='UNKNOWN',source_current_stage=None,error_message=None,lineage=[],expected_path=True,
                        reason='Explicit source trace context; completion requires workflow_completed event.',observed_at=at))
                    if run['service_id'] != row['service_id']: raise ValueError('Inconsistent service')
                    if row.get('event_type')=='workflow_started': run['started_at']=min(run['started_at'] or at,at)
                    if at>=run['last_activity']:
                        run.update(last_activity=at,source_current_stage=row['stage'])
                        if row.get('event_type')=='workflow_completed': run.update(source_status='COMPLETED',completed_at=at)
                        elif row.get('event_type')=='workflow_cancelled': run.update(source_status='CANCELLED',completed_at=at)
                except (ValueError,TypeError,KeyError):
                    if 'Malformed structured trace event for '+engine not in issues: issues.append('Malformed structured trace event for '+engine)
        except Exception:
            issues.append('Structured trace source unavailable: '+engine+'; independent sources continue')
    return list(runs.values()),events,issues

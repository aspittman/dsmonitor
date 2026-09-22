import json
import time
from collections import defaultdict
from dataclasses import asdict
from adapters.base import readonly_sqlite, readonly_postgres, timestamp, epoch
from models import ProcessStatus, StageStatus
from process_registry import REGISTRY, identify

REFERENCE_KEYS = {'intelligence_report_id', 'intelligence_report_ids', 'recommendation_ids', 'execution_request_ids', 'execution_result_ids', 'feedback_evaluation_ids', 'prediction_ids', 'correlation_id', 'organization_id', 'recommendation_id', 'execution_request_id', 'execution_result_id', 'feedback_evaluation_id', 'prediction_id'}


def references(value):
    if isinstance(value, str): value = json.loads(value or '{}')
    if not isinstance(value, dict): return {}
    from uuid import UUID
    out = {}
    for k, v in value.items():
        if k not in REFERENCE_KEYS: continue
        try: out[k] = [str(UUID(x)) for x in v] if isinstance(v, list) else str(UUID(v))
        except (ValueError, TypeError, AttributeError): continue
    return out


def collect(config):
    pg = bool(config['orchestrator_dsn'])
    connection = readonly_postgres(config['orchestrator_dsn'], config['timeout_seconds']) if pg else readonly_sqlite(config['orchestrator_sqlite'])
    with connection as db:
        marker = '%s' if pg else '?'
        allowed = config['organization_ids']
        where = (' WHERE organization_id IN (' + ','.join([marker] * len(allowed)) + ')') if allowed else ''
        # Local owner state is available without remote CRM scope. Remote state requires a scope.
        if pg and not allowed: raise ValueError('Configure organization_ids before reading remote workflow state')
        total = db.execute('SELECT count(*) AS n FROM workflow_runs' + where, allowed).fetchone()['n']
        runs = [dict(r) for r in db.execute('SELECT id,workflow_type,organization_id,status,current_stage,correlation_id,created_at,updated_at,completed_at,error_message FROM workflow_runs' + where + ' ORDER BY updated_at DESC LIMIT ' + marker, [*allowed, config['limit']])]
        ids = [r['id'] for r in runs]
        stages = []
        if ids:
            stages = [dict(s) for s in db.execute('SELECT id,workflow_run_id,stage,engine,status,attempt,started_at,completed_at,input_reference,output_reference,error_message FROM stage_runs WHERE workflow_run_id IN (' + ','.join([marker]*len(ids)) + ')', ids)]
    grouped = defaultdict(list)
    for s in stages: grouped[s['workflow_run_id']].append(s)
    processes = []
    for r in runs:
        kind = identify(r['workflow_type'])
        p = ProcessStatus(r['id'], kind, REGISTRY.get(kind, {}).get('display_name', kind), r['status'],
                          organization_id=r['organization_id'], current_stage=r['current_stage'],
                          started_at=timestamp(r['created_at']), last_activity=timestamp(r['updated_at']),
                          completed_at=timestamp(r['completed_at']), last_error=r['error_message'], correlation_id=r['correlation_id'])
        p.source_status = r['status']
        p.reason = 'Actual workflow_runs.status; stages from stage_runs. Completion is the orchestrator assertion.'
        if r['completed_at'] and r['created_at']: p.duration_seconds = round(float(r['completed_at']) - float(r['created_at']), 2)
        for s in grouped[r['id']]:
            start, end = epoch(s['started_at']), epoch(s['completed_at'])
            refs = {'input': references(s['input_reference']), 'output': references(s['output_reference'])}
            p.stages.append(asdict(StageStatus(s['stage'], s['engine'], s['status'], timestamp(s['started_at']), timestamp(s['completed_at']),
                                              round(end-start, 2) if start and end else None, max(0, s['attempt']-1), s['error_message'], refs)))
            p.stages[-1].update(attempt=s['attempt'], source_reference=s['id'])
        # Known order matches the inspected lifecycle declaration; unknown names are retained.
        order = ['research','decision','approval','execution','feedback','updated_intelligence','redecision']
        p.stages.sort(key=lambda s: (order.index(s['stage']) if s['stage'] in order else 99, s['started_at'] or '', s['stage']))
        p.error_count = sum(s['status'] == 'FAILED' for s in p.stages)
        threshold = config['stale_seconds'].get(kind, {}).get(r['current_stage'])
        if threshold and r['status'] in ('RUNNING','WAITING','PARTIAL') and time.time() - float(r['updated_at']) > float(threshold):
            p.status = 'STALE'
            p.reason = f"No workflow update within configured {threshold}s threshold; source status {r['status']}"
        processes.append(p.dict())
    return processes, {'status': 'HEALTHY', 'reason': f'Read-only workflow state available; {len(runs)} of {total} runs loaded', 'complete': total <= config['limit'], 'total': total}

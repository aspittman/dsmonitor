import json
import time
from copy import deepcopy
import pytest
from services.trace_service import normalize, project, overview
from services.snapshot_service import SnapshotStore
from services.trace_emitter import new_context, trace_event
from adapters.trace_events import collect
from service_registry import DOMAIN

NOW=1800000000

def process(stages=None, **changes):
    p=dict(process_id='run-1',process_type='domain',source='dsorchestrator',
        organization_id='org',correlation_id='shared-correlation',started_at=NOW-100,
        completed_at=None,last_activity=NOW-10,status='RUNNING',source_status='RUNNING',
        current_stage='research',last_error=None,stages=stages or [],lineage=[])
    p.update(changes)
    return p


def stage(name,engine,state='COMPLETED',attempt=1,at=NOW-10):
    from adapters.base import timestamp
    return dict(stage=name,engine=engine,status=state,attempt=attempt,started_at=timestamp(at-5),
        completed_at=timestamp(at) if state in ('COMPLETED','FAILED') else None,
        duration_seconds=5 if state in ('COMPLETED','FAILED') else None,retries=attempt-1,
        error='actual error' if state=='FAILED' else None,references={})


def trace(p,config=None):
    from adapters.base import timestamp
    p=deepcopy(p)
    for field in ('started_at','completed_at','last_activity'):p[field]=timestamp(p[field])
    runs,events=normalize([p],config or {})
    return project(runs[0],events,config or {},now=NOW)


def test_complete():
    r=trace(process([stage(s['stage'],s['engine_id']) for s in DOMAIN],source_status='COMPLETED',completed_at=NOW))
    assert r['status']=='COMPLETED' and not r['root_failure']
    assert r['duration_seconds']==100 and r['observed_execution_seconds']==30


@pytest.mark.parametrize('engine,name',[('mmonolith','research'),('decision_engine','decision'),('crm','approval'),('dsorchestrator','dispatch'),('devspace_one','execution')])
def test_root_failures(engine,name):
    stages=[stage('research','mmonolith',at=NOW-30)] if name!='research' else []
    stages.append(stage(name,engine,'FAILED'))
    r=trace(process(stages,source_status='FAILED',current_stage=name))
    assert r['cut_off_at']==engine and r['status']=='FAILED'
    assert sum(s['status']=='FAILED' for s in r['stages'])==1
    assert r['root_failure']['error_message']=='actual error'
    assert overview([r],{},now=NOW)['summary']['failed']==1


def test_downstream_not_upstream():
    r=trace(process([stage('decision','decision_engine','FAILED')],source_status='FAILED'))
    assert r['stages'][0]['status']=='NOT_STARTED'
    assert r['stages'][2]['status']=='NOT_REACHED'
    assert r['last_successful_stage'] is None


def test_waiting_approval_never_stalled():
    config={'trace_thresholds':{'domain_merchant':{'crm':{'approval':{'stalled_seconds':1,'stall_waiting':True}}}}}
    r=trace(process([stage('approval','crm','WAITING_FOR_APPROVAL',at=NOW-10000)],source_status='WAITING_FOR_APPROVAL'),config)
    assert r['status']=='WAITING_FOR_APPROVAL'
    assert all(s['status'] not in ('FAILED','STALLED','NOT_REACHED') for s in r['stages'])


def test_stall_requires_config_and_activity():
    p=process([stage('execution','devspace_one','RUNNING',at=NOW-1000)])
    assert trace(p)['status']=='RUNNING'
    config={'trace_thresholds':{'domain_merchant':{'devspace_one':{'execution':{'stalled_seconds':600,'expected_seconds':300}}}}}
    r=trace(p,config)
    assert r['status']=='STALLED' and not r['root_failure']
    assert r['current']['expected_seconds']==300


def test_retry_success_and_dedup_storage(tmp_path):
    p=process([stage('execution','devspace_one','FAILED',1,at=NOW-30),stage('execution','devspace_one','COMPLETED',2)],source_status='COMPLETED')
    r=trace(p)
    assert not r['root_failure'] and r['status']=='COMPLETED'
    execution=next(s for s in r['stages'] if s['stage']=='execution')
    assert execution['completed_after_retry'] and len(execution['attempts'])==2
    store=SnapshotStore(tmp_path/'monitor.db')
    runs,events=normalize([p],{})
    store.save_traces(runs,events);store.save_traces(runs,events)
    persisted,ev=store.traces()
    assert len(persisted)==1 and len(ev)==4


def test_legacy_and_unknown():
    r=trace(process([stage('novel','new_engine')],source='crm',process_type='future_service',correlation_id=None))
    assert r['workflow_run_id'] is None and r['correlation_quality']=='LEGACY / UNCORRELATED'
    assert len(r['stages'])==1 and r['service_id']=='future_service'
    assert overview([r],{},now=NOW)['summary']['observed_runs']==0


def test_same_correlation_does_not_merge_runs():
    runs,_=normalize([process(),process(process_id='run-2')],{})
    assert runs[0]['trace_id']!=runs[1]['trace_id']


def test_engine_unavailable_not_business_failure():
    r=trace(process([stage('research','mmonolith')]))
    result=overview([r],{},[{'engine_id':'mmonolith','availability':'OFFLINE'}],now=NOW)
    c=next(c for c in result['matrix'] if c['service_id']=='domain_merchant' and c['engine_id']=='mmonolith')
    assert c['status']=='HEALTHY' and c['availability']=='OFFLINE'


def test_emitter_safe_and_parent_context(tmp_path):
    context=new_context('new_service',workflow_run_id='existing-id',parent_run_id='parent')
    assert not trace_event(tmp_path/'missing'/'trace.jsonl',context,engine_id='mmonolith',stage='research',event_type='stage_started',status='RUNNING')
    path=tmp_path/'trace.jsonl'
    assert trace_event(path,context,engine_id='mmonolith',stage='research',event_type='stage_started',status='RUNNING')
    runs,events,issues=collect({'trace_files':{'mmonolith':str(path),'devspace_one':str(tmp_path/'absent')}})
    assert len(runs)==1 and runs[0]['parent_run_id']=='parent'
    assert events[0]['workflow_run_id']=='existing-id' and len(issues)==1


def test_cross_tenant_not_merged():
    runs,_=normalize([process(),process(organization_id='other')],{})
    assert runs[0]['trace_id']!=runs[1]['trace_id']


def test_api_and_trace_adapter_failure(tmp_path,monkeypatch):
    from app import create_app
    from config import load_config
    from adapters import dsorchestrator
    c=load_config();c.update(database=str(tmp_path/'db'),projects=str(tmp_path),crm_url='',supabase_url='',orchestrator_sqlite=str(tmp_path/'absent'),trace_files={'devspace_one':str(tmp_path/'absent')},decision_trace_log=str(tmp_path/'absent'),organization_ids=[])
    monkeypatch.setattr(dsorchestrator,'collect',lambda _:([process([stage('decision','decision_engine','FAILED')],source_status='FAILED')],{'status':'HEALTHY','complete':True,'reason':'test'}))
    app=create_app(c,start_collector=False)
    data=app.extensions['monitor'].collect()
    assert len(data['traces'])==1 and data['monitor_errors']
    client=app.test_client()
    assert len(client.get('/api/traces?failed_engine=decision_engine').json['runs'])==1
    assert client.get('/api/traces?service_id=unknown').json['runs']==[]
    assert client.get('/api/traces?from=nonsense').status_code==400
    rid=data['traces'][0]['trace_id']
    assert client.get('/api/traces/'+rid).json['status']=='FAILED'
    assert client.get('/api/traces/missing').status_code==404


def test_crm_no_action_is_not_client_work_or_approval():
    from services.process_service import crm_processes
    rows=crm_processes({'org':{'recommendations':[{'id':'no-action','organization_id':'org','recommendation_type':'NO_ACTION','status':'RECOMMENDED','created_at':'2026-09-20T00:00:00Z'}]}},[])
    assert rows[0]['process_type']=='unknown_service'
    assert rows[0]['status']=='SKIPPED'
    assert trace(rows[0])['status']=='SKIPPED'


def test_standalone_report_not_lost_or_claimed_complete():
    from services.process_service import crm_processes
    rows=crm_processes({'org':{'intelligence_reports':[{'id':'report','report_type':'DOMAIN_MARKET','correlation_id':'cycle','created_at':'2026-09-20T00:00:00Z'}]}},[])
    r=trace(rows[0])
    assert r['service_id']=='domain_merchant' and r['status']=='UNKNOWN'
    assert r['stages'][0]['status']=='COMPLETED' and r['workflow_run_id'] is None


def test_coordinator_failure_does_not_mark_unknown_upstream_not_reached():
    r=trace(process([stage('research','mmonolith')],source_status='FAILED',current_stage='execution',last_error='dispatch unavailable'))
    assert r['cut_off_at']=='dsorchestrator'
    assert r['stages'][1]['status']=='NOT_STARTED'
    assert r['stages'][3]['status']=='NOT_REACHED'


def test_wait_opt_in_and_approval_excluded_from_timing():
    waiting=process([stage('execution','devspace_one','WAITING',at=NOW-500)])
    cfg={'trace_thresholds':{'domain_merchant':{'devspace_one':{'execution':{'stalled_seconds':20}}}}}
    assert trace(waiting,cfg)['status']=='WAITING'
    cfg['trace_thresholds']['domain_merchant']['devspace_one']['execution']['stall_waiting']=True
    assert trace(waiting,cfg)['status']=='STALLED'
    r=trace(process([stage('approval','crm'),stage('execution','devspace_one')],source_status='COMPLETED'))
    assert r['observed_execution_seconds']==5
    assert next(t for t in r['engine_timings'] if t['engine_id']=='crm')['observed_execution_seconds'] is None


def test_future_service_registry_path_and_retry_events():
    cfg={'trace_registry':{'investor_research':{'configured':True,'aliases':[],'stages':[{'stage':'analyze','engine_id':'decision_engine'},{'stage':'save','engine_id':'crm'}]}}}
    r=trace(process([stage('analyze','decision_engine','FAILED')],process_type='investor_research',source_status='FAILED'),cfg)
    assert r['downstream_not_reached']==[{'engine_id':'crm','stage':'save'}]


def test_structured_context_matches_authoritative_id(tmp_path):
    context=new_context('domain_merchant',workflow_run_id='run-1')
    path=tmp_path/'events.jsonl'
    trace_event(path,context,engine_id='mmonolith',stage='research',event_type='stage_started',status='RUNNING')
    runs,_,_=collect({'trace_files':{'mmonolith':str(path)}})
    authoritative,_=normalize([process(organization_id=None)],{})
    assert runs[0]['trace_id']==authoritative[0]['trace_id']
    assert runs[0]['started_at'] is None


def test_decision_log_attribution_preserves_unknown_time(tmp_path):
    from adapters.decision_engine import service_runs
    path=tmp_path/'decision.jsonl'
    path.write_text(json.dumps({'event':'decision_completed','decision_run_id':'decision-1','organization_id':'org','strategies_rejected':['DOMAIN_ACQUISITION: No qualifying candidates'],'domain_candidate_decisions':[],'errors':[]})+'\n')
    rows=service_runs({'decision_trace_log':str(path),'organization_ids':['org']})
    assert len(rows)==1 and rows[0]['last_activity'] is None
    r=trace(rows[0])
    assert r['workflow_run_id'] is None and r['stages'][0]['status']=='COMPLETED'
    cell=next(c for c in overview([r],{},now=NOW)['matrix'] if c['service_id']=='domain_merchant' and c['engine_id']=='decision_engine')
    assert cell['status']=='UNKNOWN' and cell['failures_today']==0

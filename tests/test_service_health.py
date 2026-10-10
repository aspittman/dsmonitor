from copy import deepcopy
import pytest
from adapters.base import timestamp
from services.trace_service import overview
from services.service_health import scoped_records, pipeline
from services.snapshot_service import SnapshotStore
from test_traces import trace, process, stage, NOW

SERVICE = 'domain_merchant'


def fixture():
    contract = {'inputs': ['execution_requests'], 'outputs': ['execution_results'], 'dependencies': ['crm'],
                'activity': {'expected_interval': 86400, 'anchor_at': timestamp(NOW+100)}}
    cfg = {'organization_ids': ['org'], 'trace_registry': {SERVICE: {'engines': {'devspace_one': contract},
           'handoffs': [{'id': 'pickup', 'from': 'crm', 'to': 'devspace_one', 'table': 'execution_requests',
                         'consumer_table': 'execution_results', 'foreign_key': 'execution_request_id'}]}},
           'trace_thresholds': {SERVICE: {'handoffs': {'pickup': {'stalled_seconds': 900}}}}}
    engine = {'engine_id': 'devspace_one', 'availability': 'ONLINE', 'service_capabilities': {SERVICE: {
        'checked_at': timestamp(NOW-5), 'organization_ids':['org'], 'connectivity_status': 'CONNECTED', 'write_status': 'VERIFIED',
        'reads': {'execution_requests': {'status': 'VERIFIED', 'reason': 'GET succeeded: 0 rows'}}}}}
    engines = [engine, {'engine_id': 'crm', 'status': 'HEALTHY', 'checks': []}]
    ctx = {'org': {'_observed_at': timestamp(NOW), 'recommendations': [{'id':'rec', 'organization_id':'org', 'service_id':SERVICE}],
           'execution_requests': [{'id':'req','organization_id':'org','recommendation_id':'rec','created_at':timestamp(NOW-30)}],
           'execution_results': [{'id':'result','organization_id':'org','execution_request_id':'req','created_at':timestamp(NOW-10)}]}}
    return cfg, engines, ctx


def cell(cfg=None, engines=None, ctx=None, runs=()):
    defaults = fixture()
    o = overview(list(runs), cfg if cfg is not None else defaults[0], engines if engines is not None else defaults[1], now=NOW, contexts=ctx if ctx is not None else defaults[2])
    return next(c for c in o['matrix'] if c['service_id']==SERVICE and c['engine_id']=='devspace_one')


def test_capable_with_no_work_due_idle():
    c = cell()
    assert c['status']=='IDLE' and c['handoff_status']=='CONFIRMED'


def test_capable_confirmed_flow_healthy_without_schedule():
    cfg, eng, ctx = fixture()
    del cfg['trace_registry'][SERVICE]['engines']['devspace_one']['activity']
    assert cell(cfg,eng,ctx)['status']=='HEALTHY'


def test_successful_empty_read_is_verified():
    assert cell()['read_status']=='VERIFIED'


@pytest.mark.parametrize('dimension,value,expected', [('connectivity_status','DISCONNECTED','DISCONNECTED'), ('connectivity_status','DEGRADED','DEGRADED'), ('write_status','FAILED','DEGRADED')])
def test_engine_capability_failure(dimension,value,expected):
    cfg,eng,ctx=fixture()
    eng[0]['service_capabilities'][SERVICE][dimension]=value
    c=cell(cfg,eng,ctx)
    assert c['status']==expected and c['availability']=='ONLINE'
    if expected=='DISCONNECTED': assert c['read_status']=='UNAVAILABLE' and c['write_status']=='UNAVAILABLE'


def test_shared_crm_outage_overrides_old_success():
    cfg,eng,ctx=fixture()
    eng[0]['service_capabilities']={}
    eng[1].update(status='OFFLINE',checks=[{'status':'OFFLINE','reason':'timeout'}])
    r=trace(process([stage('execution','devspace_one',at=NOW-100000)], source_status='COMPLETED'))
    assert cell(cfg,eng,ctx,[r])['status']=='DISCONNECTED'


def test_read_denied():
    cfg,eng,ctx=fixture()
    eng[0]['service_capabilities'][SERVICE]['reads']['execution_requests']['status']='FAILED'
    assert cell(cfg,eng,ctx)['status']=='DEGRADED'


def test_no_write_history_is_unverified():
    cfg,eng,ctx=fixture()
    del eng[0]['service_capabilities'][SERVICE]['write_status']
    ctx['org']['execution_results']=[]
    c=cell(cfg,eng,ctx)
    assert c['write_status']=='UNVERIFIED' and c['status']=='UNKNOWN'


def test_real_recent_write_verified():
    cfg,eng,ctx=fixture()
    del eng[0]['service_capabilities'][SERVICE]['write_status']
    assert cell(cfg,eng,ctx)['write_status']=='VERIFIED'


@pytest.mark.parametrize('age,expected', [(30,'PENDING'), (1000,'LATE')])
def test_explicit_obligation_threshold(age,expected):
    cfg,eng,ctx=fixture()
    ctx['org']['execution_results']=[]
    ctx['org']['execution_requests'][0]['created_at']=timestamp(NOW-age)
    c=cell(cfg,eng,ctx)
    assert c['handoff_status']==expected
    if expected=='LATE': assert c['status']=='DEGRADED'


def test_no_threshold_no_invented_late():
    cfg,eng,ctx=fixture()
    cfg['trace_thresholds']={}
    ctx['org']['execution_results']=[]
    ctx['org']['execution_requests'][0]['created_at']=timestamp(NOW-100000)
    assert cell(cfg,eng,ctx)['handoff_status']=='UNKNOWN'


def test_workflow_failure_not_hidden_by_capabilities():
    r=trace(process([stage('execution','devspace_one','FAILED')],source_status='FAILED'))
    c=cell(runs=[r])
    assert c['status']=='FAILED' and c['failed_traces']==[r['trace_id']]


def test_unrelated_success_does_not_resolve_failure():
    fail=trace(process([stage('execution','devspace_one','FAILED',at=NOW-100)],source_status='FAILED'))
    success=trace(process([stage('execution','devspace_one')],process_id='unrelated',source_status='COMPLETED'))
    assert cell(runs=[fail,success])['status']=='FAILED'


def test_explicit_successful_retry_resolves_parent():
    fail=trace(process([stage('execution','devspace_one','FAILED',at=NOW-100)],source_status='FAILED'))
    success=trace(process([stage('execution','devspace_one')],process_id='retry',parent_run_id='run-1',source_status='COMPLETED'))
    assert cell(runs=[fail,success])['status']=='IDLE'


def test_upstream_failure_not_reached():
    r=trace(process([stage('decision','decision_engine','FAILED')],source_status='FAILED'))
    assert cell(runs=[r])['status']=='NOT_REACHED'


def test_waiting_approval_not_failed():
    r=trace(process([stage('approval','crm','WAITING_FOR_APPROVAL')],source_status='WAITING_FOR_APPROVAL'))
    c=cell(runs=[r])
    assert c['workflow_status']=='WAITING' and c['status'] not in ('FAILED','DEGRADED')


def test_expected_run_missing():
    cfg,eng,ctx=fixture()
    cfg['trace_registry'][SERVICE]['engines']['devspace_one']['activity'].update(anchor_at=timestamp(NOW-200),late_threshold=60)
    c=cell(cfg,eng,ctx)
    assert c['status']=='DEGRADED' and c['late_by_seconds']==140


def test_unknown_schedule_no_inactivity_penalty():
    cfg,eng,ctx=fixture()
    del cfg['trace_registry'][SERVICE]['engines']['devspace_one']['activity']
    r=trace(process([stage('execution','devspace_one',at=NOW-100000)],source_status='COMPLETED'))
    c=cell(cfg,eng,ctx,[r])
    assert c['activity_status']=='UNKNOWN' and c['status']=='HEALTHY'


def test_old_write_does_not_verify_current_permissions():
    cfg,eng,ctx=fixture()
    del eng[0]['service_capabilities'][SERVICE]['write_status']
    ctx['org']['execution_results'][0]['created_at']=timestamp(NOW-100000)
    c=cell(cfg,eng,ctx)
    assert c['write_status']=='UNVERIFIED' and c['last_write']


def test_stale_engine_report_does_not_verify_capability():
    cfg,eng,ctx=fixture()
    eng[0]['service_capabilities'][SERVICE]['checked_at']=timestamp(NOW-1000)
    c=cell(cfg,eng,ctx)
    assert c['connectivity_status']=='UNKNOWN' and c['read_status']=='UNKNOWN'


def test_legacy_uncorrelated_and_cross_tenant_never_prove_consumption():
    cfg,eng,ctx=fixture()
    ctx['org']['execution_results'][0]['execution_request_id']='unrelated'
    assert cell(cfg,eng,ctx)['handoff_status']=='PENDING'
    ctx['org']['execution_results'][0].update(execution_request_id='req',organization_id='other')
    assert cell(cfg,eng,ctx)['handoff_status']=='PENDING'


def test_service_failure_isolated():
    r=trace(process([stage('execution','devspace_one','FAILED')],service_id='devspace_services',source_status='FAILED'))
    assert cell(runs=[r])['status']=='IDLE'


def test_monitor_credentials_never_prove_engine_reads():
    cfg,eng,ctx=fixture()
    eng[0]['service_capabilities']={}
    assert cell(cfg,eng,ctx)['read_status']=='UNKNOWN'


def test_crm_empty_context_read_valid():
    cfg,eng,ctx=fixture()
    cfg['trace_registry'][SERVICE]['engines']['crm']={'inputs':['execution_requests'],'outputs':[], 'dependencies':['supabase']}
    ctx['org']['execution_requests']=[]
    c=next(c for c in overview([],cfg,eng,now=NOW,contexts=ctx)['matrix'] if c['engine_id']=='crm' and c['service_id']==SERVICE)
    assert c['read_status']=='VERIFIED' and c['connectivity_status']=='CONNECTED'


def test_transition_recovery_and_restart(tmp_path):
    store=SnapshotStore(tmp_path/'monitor.db')
    c=cell()
    c.update(status='DISCONNECTED',reason='CRM timed out')
    store.service_health([c]); store.service_health([c])
    assert len(c['health_history'])==1
    store=SnapshotStore(tmp_path/'monitor.db')
    c.update(status='IDLE',reason='No work due')
    store.service_health([c])
    assert len(c['health_history'])==2 and c['recovered_at'] and c['previous_issue']=='CRM timed out'


def test_not_configured_does_not_count_as_problem():
    result=overview([],{},now=NOW)
    cells={c['engine_id']:c for c in result['matrix'] if c['service_id']=='investor_research'}
    assert cells['devspace_one']['status']=='NOT_CONFIGURED'
    assert cells['dsorchestrator']['status']=='UNKNOWN'
    assert all(cells[e]['status']=='UNKNOWN' for e in ('mmonolith','decision_engine','crm'))
    assert not result['pipeline_problems']


def test_structured_read_requires_exact_reference_and_not_stage_completion():
    cfg,eng,ctx=fixture()
    ctx['org']['execution_results']=[]
    r=trace(process([stage('execution','devspace_one','RUNNING')]))
    event={'trace_id':r['trace_id'],'trace_event_id':'receipt','engine_id':'devspace_one','organization_id':'org',
           'workflow_run_id':'run-1','event_type':'read_succeeded','status':'COMPLETED','stage':'execution',
           'timestamp':timestamp(NOW-5),'metadata':{'table':'execution_requests','record_id':'req'},'attempt':1}
    r['events'].append(event)
    from services.trace_service import project
    projected=project(r,r['events'],cfg,now=NOW)
    assert next(s for s in projected['stages'] if s['engine_id']=='devspace_one')['status']=='RUNNING'
    assert cell(cfg,eng,ctx,[projected])['handoff_status']=='CONFIRMED'
    event['metadata']['record_id']='different'
    assert cell(cfg,eng,ctx,[r])['handoff_status']=='PENDING'


def test_structured_persistence_proves_write_only_with_table_and_id():
    cfg,eng,ctx=fixture()
    ctx['org']['execution_results']=[]
    del eng[0]['service_capabilities'][SERVICE]['write_status']
    r=trace(process([stage('execution','devspace_one','RUNNING')]))
    event={'trace_id':r['trace_id'],'trace_event_id':'write','engine_id':'devspace_one','organization_id':'org',
           'workflow_run_id':'run-1','event_type':'write_persisted','status':'COMPLETED','stage':'execution',
           'timestamp':timestamp(NOW-5),'metadata':{'table':'execution_results','record_id':'result'}}
    r['events'].append(event)
    assert cell(cfg,eng,ctx,[r])['write_status']=='VERIFIED'
    del event['metadata']['record_id']
    assert cell(cfg,eng,ctx,[r])['write_status']=='UNVERIFIED'


def test_approval_not_expected_and_cancelled_work_not_late():
    cfg,eng,ctx=fixture()
    cfg['trace_registry'][SERVICE]['handoffs'][0]['approval_required']=True
    ctx['org']['execution_results']=[]
    ctx['org']['execution_requests'][0]['created_at']=timestamp(NOW-10000)
    assert cell(cfg,eng,ctx)['handoff_status']=='NOT_EXPECTED'
    ctx['org']['execution_requests'][0].update(approved_at=timestamp(NOW-10000),approved_by='admin',status='CANCELLED')
    assert cell(cfg,eng,ctx)['handoff_status']=='NOT_EXPECTED'


def test_failed_workflow_still_failed_after_unrelated_handoff():
    r=trace(process([stage('execution','devspace_one','FAILED')],source_status='FAILED'))
    c=cell(runs=[r])
    assert c['handoff_status']=='CONFIRMED' and c['status']=='FAILED'


def test_unknown_does_not_signal_recovery(tmp_path):
    store=SnapshotStore(tmp_path/'monitor.db')
    c=cell(); c.update(status='FAILED',reason='Workflow failed'); store.service_health([c])
    c.update(status='UNKNOWN',reason='Probe unavailable'); store.service_health([c])
    assert c['recovered_at'] is None


def test_live_probe_cache_keeps_original_observation(tmp_path, monkeypatch):
    from services.monitor import Monitor
    monitor=Monitor({'database':str(tmp_path/'m.db'),'retention_days':1,'capability_seconds':60})
    calls=[]
    def collect():
        calls.append(1)
        return {'status':'HEALTHY','checks':[]}
    first=monitor.cached_probe('db',collect)
    first['checks'].append('must not mutate cache')
    second=monitor.cached_probe('db',collect)
    assert len(calls)==1 and second['checks']==[] and first['observed_at']==second['observed_at']


def test_engine_reports_no_work_without_schedule():
    cfg,eng,ctx=fixture()
    del cfg['trace_registry'][SERVICE]['engines']['devspace_one']['activity']
    eng[0]['service_capabilities'][SERVICE]['work_expected']=False
    assert cell(cfg,eng,ctx)['status']=='IDLE'


def test_capability_requires_configured_tenant_scope():
    cfg,eng,ctx=fixture()
    eng[0]['service_capabilities'][SERVICE]['organization_ids']=['other']
    assert cell(cfg,eng,ctx)['read_status']=='UNKNOWN'


def test_write_evidence_required_in_every_monitored_tenant():
    cfg,eng,ctx=fixture()
    cfg['organization_ids'].append('other')
    assert cell(cfg,eng,ctx)['write_status']=='UNVERIFIED'


def test_real_claim_is_consumption_before_result_exists():
    cfg,eng,ctx=fixture()
    cfg['trace_registry'][SERVICE]['handoffs'][0].update(receipt_statuses=['RUNNING'],receipt_timestamp='updated_at')
    ctx['org']['execution_results']=[]
    ctx['org']['execution_requests'][0].update(status='RUNNING',updated_at=timestamp(NOW-10),created_at=timestamp(NOW-2000))
    assert cell(cfg,eng,ctx)['handoff_status']=='CONFIRMED'


def test_phase_specific_cutoff_does_not_confuse_repeated_crm_edges():
    r=trace(process([stage('decision','decision_engine','FAILED')],source_status='FAILED'))
    edges=overview([r],{},now=NOW)['pipelines'][SERVICE]
    assert next(e for e in edges if e['id']=='intelligence_read')['status']=='UNKNOWN'
    assert next(e for e in edges if e['id']=='result_write')['status']=='NOT_REACHED'


def test_monitor_permission_denied_does_not_claim_engine_dependency_failure():
    cfg,eng,ctx=fixture()
    cfg['trace_registry'][SERVICE]['engines']['devspace_one']['dependencies']=['supabase']
    eng[0]['service_capabilities']={}
    eng.append({'engine_id':'supabase','status':'ONLINE','dependency_status':'UNKNOWN',
                'checks':[{'name':'Database connectivity','status':'ONLINE'}, {'name':'Monitoring read access','status':'ERROR'}]})
    c=cell(cfg,eng,ctx)
    assert c['status']=='UNKNOWN' and c['connectivity_status']=='UNKNOWN'


def test_explicit_report_use_by_legacy_no_action_is_proven_without_relabeling_recommendation():
    ctx={'org': {'_observed_at':timestamp(NOW),
        'intelligence_reports':[{'id':'report','organization_id':'org','report_type':'DOMAIN_MARKET','created_at':timestamp(NOW-30)}],
        'recommendations':[{'id':'no-action','organization_id':'org','recommendation_type':'NO_ACTION'}],
        'recommendation_evidence':[{'id':'evidence','organization_id':'org','recommendation_id':'no-action','intelligence_report_id':'report'}]}}
    o=overview([],{},now=NOW,contexts=ctx)
    edges=o['pipelines'][SERVICE]
    assert next(e for e in edges if e['id']=='intelligence_read')['status']=='CONFIRMED'
    assert next(e for e in edges if e['id']=='recommendation_write')['status']=='UNKNOWN'


def test_explicit_write_failure_is_not_hidden_by_reported_permissions():
    r=trace(process([stage('execution','devspace_one','RUNNING')]))
    r['events'].append({'trace_id':r['trace_id'],'trace_event_id':'write-failure','engine_id':'devspace_one',
       'organization_id':'org','event_type':'write_persisted','status':'FAILED',
       'timestamp':timestamp(NOW-1),'metadata':{'table':'execution_results'}})
    c=cell(runs=[r])
    assert c['write_status']=='FAILED' and c['status']=='DEGRADED'

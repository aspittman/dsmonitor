import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4
import pytest
from app import create_app
from config import load_config
from adapters import crm, supabase, dsorchestrator
from adapters.base import readonly_sqlite, timestamp
from services.monitor import Monitor
from services.security import Sanitizer
from services.workflow_trace_service import enrich
from services.process_service import crm_processes

ORG='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'

@pytest.fixture
def config(tmp_path):
    c=load_config()
    c.update(capability_files={},projects=str(tmp_path),database=str(tmp_path/'monitor.db'),crm_url='',crm_token='',supabase_url='',supabase_key='',supabase_dsn='',orchestrator_dsn='',organization_ids=[],secrets=['extremely-private-secret'],orchestrator_sqlite=str(tmp_path/'source.db'),health_urls={},heartbeat_files={},stale_seconds={})
    return c


def source(config, status='RUNNING', age=10):
    now=time.time()-age
    db=sqlite3.connect(config['orchestrator_sqlite'])
    db.executescript('''CREATE TABLE workflow_runs(id TEXT, workflow_type TEXT, organization_id TEXT,status TEXT,current_stage TEXT,correlation_id TEXT,created_at REAL,updated_at REAL,completed_at REAL,error_message TEXT);
    CREATE TABLE stage_runs(id TEXT,workflow_run_id TEXT,stage TEXT,engine TEXT,status TEXT,attempt INTEGER,started_at REAL,completed_at REAL,input_reference TEXT,output_reference TEXT,error_message TEXT);''')
    db.execute('INSERT INTO workflow_runs VALUES(?,?,?,?,?,?,?,?,?,?)',('run1','domain',ORG,status,'execution',str(uuid4()),now-100,now,None,None))
    db.execute('INSERT INTO stage_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)',('stage1','run1','execution','devspace_one',status,3,now-100,now if status=='FAILED' else None,'{}','{}','password=extremely-private-secret' if status=='FAILED' else None))
    db.commit();db.close()


def test_readonly_source_rejects_mutation(config):
    source(config)
    with readonly_sqlite(config['orchestrator_sqlite']) as db:
        with pytest.raises(sqlite3.OperationalError): db.execute('DELETE FROM workflow_runs')
    p,c=dsorchestrator.collect(config)
    assert len(p)==1 and c['complete']
    assert p[0]['stages'][0]['retries']==2


def test_missing_sqlite_is_not_created(config):
    with pytest.raises(FileNotFoundError):
        with readonly_sqlite(config['orchestrator_sqlite']): pass
    assert not Path(config['orchestrator_sqlite']).exists()


@pytest.mark.parametrize('outage',['crm','supabase','both'])
def test_dependency_outages_do_not_crash_dashboard(config,monkeypatch,outage):
    source(config)
    config.update(crm_url='http://127.0.0.1:1',crm_token='test',supabase_url='http://127.0.0.1:1',supabase_key='test')
    def offline(*a,**k):raise ConnectionError('Endpoint unreachable or timed out')
    monkeypatch.setattr(crm,'get_json',offline if outage in ('crm','both') else lambda *a,**k:{'success':True,'data':[]})
    monkeypatch.setattr(supabase,'get_json',offline if outage in ('supabase','both') else lambda *a,**k:[])
    app=create_app(config,start_collector=False)
    app.extensions['monitor'].collect()
    client=app.test_client()
    assert client.get('/').status_code==200
    data=client.get('/api/status').json
    assert len(data['engines'])==6 and data['processes'][0]['process_id']=='run1'
    for e in data['engines']:
        if e['engine_id']==outage or outage=='both' and e['infrastructure']:assert e['status']=='OFFLINE'
    assert data['summary']['active_processes']==1


def test_adapter_failure_isolated(config,monkeypatch):
    from adapters import devspace_one
    def broken(*a):raise ValueError('secret data')
    monkeypatch.setattr(devspace_one,'collect',broken)
    data=Monitor(config).collect()
    assert len(data['engines'])==6
    assert next(e for e in data['engines'] if e['engine_id']=='devspace_one')['status']=='UNKNOWN'
    assert 'secret data' not in json.dumps(data)


def test_sanitization_at_display_and_storage(config):
    source(config,'FAILED')
    monitor=Monitor(config);data=monitor.collect()
    text=json.dumps(data)+json.dumps(monitor.store.history())+json.dumps(monitor.store.history('events'))
    assert 'extremely-private-secret' not in text
    assert '[REDACTED]' in text
    assert data['errors'][0]['retries']==2


@pytest.mark.parametrize('value',['Authorization: Bearer abcdefgh','password="hello world"','postgresql://u:pass@host/db','user@example.com','token=abcdefg','eyJhbGciOiJIUzI1NiJ9.abcdef.abcdef'])
def test_secret_formats(value):
    clean=Sanitizer().text(value)
    assert 'REDACTED' in clean and clean!=value


def test_tenant_mismatch_rejected(config,monkeypatch):
    config.update(crm_url='http://localhost:1',crm_token='test',organization_ids=[ORG])
    def fake(url,*a,**k):
        return {'success':True,'data':[{'id':ORG}] if url.endswith('organizations') else {'recommendations':[{'id':'x','organization_id':OTHER}]}}
    monkeypatch.setattr(crm,'get_json',fake)
    engine,contexts,orgs=crm.collect(config)
    assert engine['status']=='DEGRADED' and not contexts


def test_scope_filters_local_workflows(config):
    source(config);config['organization_ids']=[OTHER]
    p,c=dsorchestrator.collect(config)
    assert not p and c['total']==0


def test_stale_threshold_is_opt_in(config):
    source(config,age=7200)
    assert dsorchestrator.collect(config)[0][0]['status']=='RUNNING'
    config['stale_seconds']={'domain':{'execution':600}}
    p=dsorchestrator.collect(config)[0][0]
    assert p['status']=='STALE' and '600' in p['reason']


def test_lineage_never_joins_by_time_or_other_tenant(config):
    rid=str(uuid4());other=str(uuid4())
    p={'organization_id':ORG,'stages':[{'stage':'research','references':{'output':{'intelligence_report_id':rid}}}]}
    ctx={ORG:{'intelligence_reports':[{'id':rid,'organization_id':OTHER},{'id':other,'organization_id':ORG}]}}
    assert enrich([p],ctx)[0]['lineage']==[{'table':'intelligence_reports','id':rid,'via':'stage research','verified':False,'status':'UNVERIFIED','timestamp':None,'is_test':None,'observed_at':None}]


def test_mutations_and_remote_access_rejected(config):
    app=create_app(config,False);client=app.test_client()
    assert client.post('/api/status').status_code==405
    assert client.get('/api/status',headers={'Host':'attacker.example'}).status_code==403
    assert client.get('/api/status',environ_base={'REMOTE_ADDR':'192.0.2.1'}).status_code==403
    assert client.get('/').headers['Content-Security-Policy'].startswith("default-src 'self'")


def test_missing_coverage_not_zero(config):
    data=Monitor(config).collect()
    assert data['summary']['active_processes'] is None
    assert data['summary']['errors_today'] is None
    assert data['processes']==[]


def test_history_deduplicates_events(config):
    source(config,'FAILED');m=Monitor(config);m.collect();m.collect()
    assert len(m.store.history('events'))==1


def test_timestamp_offsets():
    assert timestamp('2026-09-17T01:00:00-06:00')=='2026-09-17T07:00:00+00:00'
    assert timestamp('invalid') is None


def test_unwritable_history_does_not_break_live(config):
    config['database']='/proc/not-a-monitor.db'
    m=Monitor(config);data=m.collect()
    assert len(data['engines'])==6 and data['monitor_errors']


def test_crm_only_process_uses_real_records():
    rid=str(uuid4());report_id=str(uuid4())
    ctx={ORG:{'recommendations':[{'id':rid,'organization_id':ORG,'recommendation_type':'DOMAIN_ACQUISITION','status':'RECOMMENDED','created_at':'2026-09-17T00:00:00Z'}],
              'intelligence_reports':[{'id':report_id,'organization_id':ORG,'created_at':'2026-09-16T00:00:00Z'}],
              'recommendation_evidence':[{'recommendation_id':rid,'intelligence_report_id':report_id}]}}
    p=crm_processes(ctx,[])[0]
    assert p['status']=='WAITING_FOR_APPROVAL'
    assert [s['stage'] for s in p['stages']]==['research','decision']
    assert p['completed_at'] is None


def test_undated_errors_remain_visible_without_invented_time(config):
    logdir=Path(config['projects'])/'devspace-one/logs';logdir.mkdir(parents=True)
    (logdir/'worker.log').write_text("Traceback (most recent call last):\n  File 'worker.py', line 2\nModuleNotFoundError: No module named 'core'\n")
    m=Monitor(config);data=m.collect()
    assert len(data['errors'])==1
    assert data['errors'][0]['timestamp'] is None
    assert data['errors'][0]['observed_at']
    assert 'No module named' in data['errors'][0]['message']
    m.collect()
    assert len(m.store.history('events'))==1


def test_malformed_crm_record_does_not_hide_independent_workflows(config,monkeypatch):
    source(config)
    from models import EngineStatus
    monkeypatch.setattr(crm,'collect',lambda *a:(EngineStatus('crm','CRM',status='HEALTHY',infrastructure=True).dict(),{ORG:{'recommendations':[{'id':'broken'}]}},[]))
    data=Monitor(config).collect()
    assert len(data['engines'])==6
    assert data['processes'][0]['process_id']=='run1'
    assert data['monitor_errors']


def test_crm_context_and_capability_have_separate_cache_ttls(config,monkeypatch):
    config.update(capability_seconds=60,crm_context_seconds=900)
    config.update(crm_url='http://localhost:1',crm_token='test',organization_ids=[ORG])
    calls=[]
    def get(url,*a,**k):
        calls.append(url)
        return {'success':True,'data':[{'id':ORG}] if url.endswith('organizations') else {'recommendations':[]}}
    monkeypatch.setattr(crm,'get_json',get)
    cache={};crm.collect(config,cache);crm.collect(config,cache)
    assert sum(x.endswith('organizations') for x in calls)==1
    at, rows, observed_at = cache['_organizations']
    cache['_organizations']=(at-61, rows, observed_at)
    crm.collect(config,cache)
    assert sum(x.endswith('organizations') for x in calls)==2
    assert sum(x.endswith('monitoring-context') for x in calls)==1  # One bounded context endpoint, cached independently.


def test_full_source_trace_uses_only_id_links(config):
    """Synthetic fixture of the inspected source schema, never operational data."""
    source(config,status='COMPLETED')
    tables=['intelligence_reports','recommendations','execution_requests','execution_results','feedback_evaluations','intelligence_reports','recommendations']
    names=['research','decision','approval','execution','feedback','updated_intelligence','redecision']
    keys=['intelligence_report_id','recommendation_ids','execution_request_ids','execution_result_ids','feedback_evaluation_ids','intelligence_report_id','recommendation_ids']
    owners=['mmonolith','decision_engine','crm','devspace_one','mmonolith','mmonolith','decision_engine']
    contexts={ORG:{'_observed_at':timestamp(time.time())}}
    with sqlite3.connect(config['orchestrator_sqlite']) as db:
        db.execute('DELETE FROM stage_runs')
        for i,(name,key,table,owner) in enumerate(zip(names,keys,tables,owners)):
            rid=str(uuid4());output={key:[rid] if key.endswith('_ids') else rid}
            contexts[ORG].setdefault(table,[]).append({'id':rid,'organization_id':ORG,'status':'COMPLETED','created_at':timestamp(time.time()-100+i),'is_test':True})
            db.execute('INSERT INTO stage_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(str(uuid4()),'run1',name,owner,'COMPLETED',1,time.time()-110+i,time.time()-100+i,'{}',json.dumps(output),None))
    processes,_=dsorchestrator.collect(config);enrich(processes,contexts)
    assert len(processes[0]['stages'])==7
    assert len(processes[0]['lineage'])==7
    assert all(n['verified'] for n in processes[0]['lineage'])
    assert all(s['duration_seconds'] is not None for s in processes[0]['stages'])


def test_limited_workflow_window_does_not_claim_complete_totals(config):
    source(config)
    with sqlite3.connect(config['orchestrator_sqlite']) as db:
        db.execute("INSERT INTO workflow_runs SELECT 'run2',workflow_type,organization_id,status,current_stage,correlation_id,created_at,updated_at,completed_at,error_message FROM workflow_runs")
    config['limit']=1
    data=Monitor(config).collect()
    assert data['coverage']['total']==2 and not data['coverage']['complete']
    assert data['summary']['active_processes'] is None


def test_api_availability_count_survives_dependency_degradation(config,monkeypatch):
    from adapters import decision_engine
    from models import EngineStatus
    engine=EngineStatus('decision_engine','Decision Engine',status='HEALTHY').dict()
    engine['checks']=[{'name':'API','status':'HEALTHY','reason':'OK'}]
    monkeypatch.setattr(decision_engine,'collect',lambda c:engine)
    db=EngineStatus('supabase','Supabase',status='OFFLINE',infrastructure=True).dict()
    monkeypatch.setattr(supabase,'collect',lambda c:db)
    data=Monitor(config).collect()
    assert data['summary']['engines_online']==1
    assert data['engines'][1]['status']=='DEGRADED'


def test_naive_log_time_requires_explicit_timezone(config):
    from adapters.local import collect_logs
    root=Path(config['projects']);(root/'logs').mkdir()
    (root/'logs/events.log').write_text('2026-09-17 12:00:00 ERROR something failed\n')
    unknown=collect_logs(root,'test')[1][0]
    assert unknown['timestamp'] is None
    known=collect_logs(root,'test',log_timezone='America/Denver')[1][0]
    assert known['timestamp']=='2026-09-17T18:00:00+00:00'


def test_structured_log_error_field_null_is_not_failure(config):
    from adapters.local import collect_logs
    root=Path(config['projects']);(root/'logs').mkdir()
    (root/'logs/events.log').write_text(json.dumps({'timestamp':'2026-09-17T12:00:00Z','status':'COMPLETED','error':None}))
    activity,errors=collect_logs(root,'test')
    assert len(activity)==1 and not errors


def test_database_monitor_auth_failure_does_not_prove_engine_database_failure(config,monkeypatch):
    config.update(supabase_url='https://example.invalid',supabase_key='test')
    def denied(*a,**k):raise ConnectionError('HTTP 401')
    monkeypatch.setattr(supabase,'get_json',denied)
    result=supabase.collect(config)
    assert result['status']=='UNKNOWN' and result['dependency_status']=='UNKNOWN'


def test_stale_running_workflow_remains_in_source_active_total(config):
    source(config,age=7200);config['stale_seconds']={'domain':{'execution':600}}
    result=Monitor(config).collect()
    assert result['processes'][0]['status']=='STALE'
    assert result['summary']['active_processes']==1


def test_repeated_tracebacks_do_not_crowd_out_other_services(config):
    from adapters.local import collect_logs
    root=Path(config['projects']);(root/'logs').mkdir()
    for name,message in [('a','ModuleNotFoundError: first service'),('b','RuntimeError: second service')]:
        (root/'logs'/f'{name}.log').write_text((message+'\n')*60)
    _,errors=collect_logs(root,'test')
    assert len(errors)==2
    assert all(e['occurrences_in_tail']==60 for e in errors)


def test_postgres_permission_denied_proves_response_not_engine_failure(config,monkeypatch):
    from adapters.base import HTTPReadError
    config.update(supabase_url='https://example.invalid',supabase_key='test')
    def denied(*a,**k):raise HTTPReadError(401,'42501')
    monkeypatch.setattr(supabase,'get_json',denied)
    result=supabase.collect(config)
    assert result['status']=='ONLINE'
    assert result['dependency_status']=='UNKNOWN'
    assert '42501' in result['monitoring_issue']
    assert result['checks'][0]['name']=='Database connectivity'


@pytest.mark.parametrize('code',[401,403,404,405])
def test_crm_monitor_access_gap_does_not_degrade_every_engine(config,monkeypatch,code):
    from adapters.base import HTTPReadError
    config.update(crm_url='https://example.invalid',crm_token='test')
    def denied(*a,**k):raise HTTPReadError(code)
    monkeypatch.setattr(crm,'get_json',denied)
    result=Monitor(config).collect()
    assert result['engines'][4]['status']=='UNKNOWN'
    assert result['engines'][4]['monitoring_issue']
    assert all(e['status']=='UNKNOWN' for e in result['engines'][:4])
    assert result['summary']['engines_degraded']==0


def test_http_read_error_retains_only_safe_code(monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError
    from adapters import base
    body=BytesIO(b'{"code":"42501","message":"private password=secret-token"}')
    class Opener:
        def open(self,*a,**k):raise HTTPError('https://example.invalid',401,'Unauthorized',{},body)
    monkeypatch.setattr(base,'build_opener',lambda *a:Opener())
    with pytest.raises(base.HTTPReadError) as caught:base.get_json('https://example.invalid')
    assert caught.value.database_code=='42501'
    assert str(caught.value)=='HTTP 401'
    assert 'secret-token' not in repr(caught.value.__dict__)
    assert body.closed


def test_real_dependency_server_failure_still_degrades_engine(config,monkeypatch):
    from adapters.base import HTTPReadError
    config.update(crm_url='https://example.invalid',crm_token='test')
    def unavailable(*a,**k):raise HTTPReadError(503)
    monkeypatch.setattr(crm,'get_json',unavailable)
    result=Monitor(config).collect()
    assert result['summary']['engines_degraded']==4
    assert result['engines'][4]['status']=='ERROR'

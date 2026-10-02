from copy import deepcopy
from adapters.base import timestamp, HTTPReadError
from services.freshness import project, readiness
from scripts.capability_probe import probe

NOW=1800000000
ORG='11111111-1111-4111-8111-111111111111'


def healthy():
    return {'checked_at':timestamp(NOW), 'organization_ids':[ORG], 'connectivity_status':'CONNECTED',
            'configuration_status':'VERIFIED','reads':{'execution_requests':{'status':'VERIFIED'}}}


def snapshot():
    return {'collected_at':timestamp(NOW), 'engines':[{'engine_id':'devspace_one','service_capabilities':{'domain_merchant':healthy()},'status':'FAILED','last_success':timestamp(NOW-86400)}],
      'trace_overview':{'matrix':[{'engine_id':'devspace_one','service_id':'domain_merchant','status':'FAILED','workflow_status':'FAILED','handoff_status':'PENDING','last_success':timestamp(NOW-86400)}]}}


def test_current_readiness_independent_of_failed_workflow():
    data=project(snapshot(),{'organization_ids':[ORG]},NOW)
    engine=data['engines'][0]; cell=data['trace_overview']['matrix'][0]
    assert engine['status']=='READY'
    assert cell['workflow_status']=='FAILED' and cell['status']=='READY'
    assert cell['workflow_progress']['status']=='PENDING'
    assert cell['last_run_outcome']['status']=='UNKNOWN' # No invented run from a failure aggregate.


def test_expiry_applied_at_api_read_time_without_new_collection():
    raw=snapshot()
    cfg={'organization_ids':[ORG], 'snapshot_max_age_seconds':45}
    data=project(raw,cfg,NOW+46)
    assert data['engines'][0]['status']=='STALE'
    assert data['trace_overview']['matrix'][0]['status']=='STALE'
    assert data['trace_overview']['matrix'][0]['last_run_outcome']['last_success']==timestamp(NOW-86400)
    assert raw['engines'][0]['status']=='FAILED' # Never mutate or re-date source evidence.


def test_old_capability_expires_even_while_collector_updates():
    raw=snapshot();raw['collected_at']=timestamp(NOW+100)
    data=project(raw,{'organization_ids':[ORG],'engine_capability_seconds':90},NOW+100)
    assert data['engines'][0]['status']=='STALE'
    assert data['trace_overview']['matrix'][0]['connectivity_status']=='UNKNOWN'


def test_scope_future_timestamp_and_missing_configuration_never_ready():
    report=healthy()
    assert readiness(report,['other'],90,NOW)['status']=='UNKNOWN'
    report['checked_at']=timestamp(NOW+1)
    assert readiness(report,[ORG],90,NOW)['status']=='UNKNOWN'
    report['checked_at']=timestamp(NOW);report['configuration_status']='MISSING'
    assert readiness(report,[ORG],90,NOW)['status']=='BLOCKED'


PROFILE={'engine_id':'devspace_one','url_env':'URL','secret_env':'SECRET','services':{'domain_merchant':{'inputs':['execution_requests']}}}
ENV={'URL':'https://crm.example','SECRET':'value'}


def test_missing_endpoint_never_downloads_unbounded_history():
    calls=[]
    def missing(url,*args):
        calls.append(url);raise HTTPReadError(404)
    result=probe(PROFILE,[ORG],ENV,get=missing)['service_capabilities']['domain_merchant']
    assert calls==['https://crm.example/api/bot/monitoring-capabilities']
    assert result['connectivity_status']=='UNKNOWN'
    assert 'Deploy' in result['next_action']


def test_probe_read_access_and_adapter_readiness_are_separate():
    def get(*args):
        return {'success':True,'data':{'organization_id':ORG,'engine_id':'devspace_one','service_id':'domain_merchant',
            'connectivity_status':'CONNECTED','reads':{'execution_requests':{'status':'VERIFIED'}},
            'configuration':{'verified':True,'service_enabled':True,'adapter_ready':False}}}
    r=probe(PROFILE,[ORG],ENV,get=get)['service_capabilities']['domain_merchant']
    assert r['connectivity_status']=='CONNECTED' and r['configuration_status']=='BLOCKED'
    assert r['write_status']=='UNVERIFIED'


def test_probe_permission_failure_and_tenant_mismatch():
    def denied(*args): raise HTTPReadError(403)
    assert probe(PROFILE,[ORG],ENV,get=denied)['service_capabilities']['domain_merchant']['connectivity_status']=='DEGRADED'
    def wrong(*args):return {'success':True,'data':{'organization_id':'other'}}
    assert probe(PROFILE,[ORG],ENV,get=wrong)['service_capabilities']['domain_merchant']['connectivity_status']=='UNKNOWN'


def test_partial_scope_does_not_verify_configuration():
    def get(url,timeout,headers,query):
        if 'other' in query: raise ConnectionError()
        return {'success':True,'data':{'organization_id':ORG,'engine_id':'devspace_one','service_id':'domain_merchant','connectivity_status':'CONNECTED','reads':{'execution_requests':{'status':'VERIFIED'}},'configuration':{'verified':True,'service_enabled':True}}}
    r=probe(PROFILE,[ORG,'other'],ENV,get=get)['service_capabilities']['domain_merchant']
    assert r['connectivity_status']=='DISCONNECTED' and r['configuration_status']=='UNVERIFIED'


def test_unregistered_fragment_does_not_erase_registered_readiness():
    raw=snapshot()
    raw['trace_overview']['matrix'].append({'engine_id':'devspace_one','service_id':'unknown_service','status':'UNKNOWN'})
    assert project(raw,{'organization_ids':[ORG]},NOW)['engines'][0]['status']=='READY'


def test_disabled_service_is_not_a_broken_adapter():
    r=healthy();r['configuration_status']='BLOCKED';r['configuration_checks']=[{'verified':True,'service_enabled':False,'adapter_ready':False}]
    assert readiness(r,[ORG],90,NOW)['status']=='NOT_CONFIGURED'


def test_crm_unconfigured_relationship_stays_unconfigured():
    raw=snapshot();raw['engines']=[{'engine_id':'crm','infrastructure':True,'status':'HEALTHY'}]
    raw['trace_overview']['matrix']=[{'engine_id':'crm','service_id':'future_service','status':'NOT_CONFIGURED'}]
    assert project(raw,{'organization_ids':[ORG]},NOW)['trace_overview']['matrix'][0]['status']=='NOT_CONFIGURED'


def test_healthz_and_status_expire_when_collector_stops(tmp_path):
    from app import create_app
    from config import load_config
    import time
    config=load_config();config.update(database=str(tmp_path/'monitor.db'),organization_ids=[ORG])
    app=create_app(config,start_collector=False)
    raw=snapshot();raw['collected_at']=timestamp(time.time()-46)
    app.extensions['monitor'].data=raw
    with app.test_client() as client:
        assert client.get('/healthz').status_code==503
        assert client.get('/api/status').json['engines'][0]['status']=='STALE'


def test_integrated_probe_scheduler_repeats_without_business_jobs(tmp_path,monkeypatch):
    from services.monitor import Monitor
    from config import load_config
    config=load_config();config.update(database=str(tmp_path/'monitor.db'),probe_interval_seconds=1,refresh_seconds=1)
    monitor=Monitor(config);calls=[]
    def cycle(settings):
        calls.append(settings)
        if len(calls)==2:monitor.stop.set()
    monkeypatch.setattr('scripts.engine_capabilities.cycle',cycle)
    monkeypatch.setattr(monitor,'collect',lambda:None)
    monitor.start();monitor.probe_thread.join(timeout=3);monitor.thread.join(timeout=3)
    monitor.stop.set()
    assert len(calls)==2


def test_infrastructure_cache_cadence_does_not_flicker_stale():
    raw=snapshot();raw['collected_at']=timestamp(NOW+50)
    raw['engines']=[{'engine_id':'supabase','infrastructure':True,'observed_at':timestamp(NOW),'status':'HEALTHY'}]
    raw['trace_overview']['matrix']=[]
    result=project(raw,{'capability_seconds':45,'engine_capability_seconds':90},NOW+50)
    assert result['engines'][0]['status']=='READY'


def test_monitor_permission_gap_is_not_reported_ready_or_engine_outage():
    raw=snapshot();raw['engines']=[{'engine_id':'supabase','infrastructure':True,'observed_at':timestamp(NOW),'status':'ONLINE','monitoring_issue':'Monitoring read permission denied (42501)'}]
    raw['trace_overview']['matrix']=[]
    result=project(raw,{},NOW)['engines'][0]
    assert result['status']=='BLOCKED'
    assert '42501' in result['readiness']['reason']
    assert 'engine access' in result['readiness']['next_action']


def test_unsupported_service_contract_is_unknown_not_permission_failure():
    def unsupported(*args): raise HTTPReadError(400)
    result = probe(PROFILE, [ORG], ENV, get=unsupported)['service_capabilities']['domain_merchant']
    assert result['connectivity_status'] == 'UNKNOWN'
    assert result['configuration_status'] == 'UNVERIFIED'
    assert 'unsupported' in result['reason']
    assert readiness(result, [ORG], 90, __import__('time').time())['status'] == 'UNKNOWN'

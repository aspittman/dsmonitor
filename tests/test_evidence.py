from services.evidence_service import provenance, shared_state
from services.trace_service import normalize, project

ORG='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'
AT='2026-09-25T01:00:00+00:00'


def context():
    return {ORG:{'_observed_at':AT,
        'intelligence_reports':[{'id':'report','organization_id':ORG,'report_type':'DOMAIN_MARKET','created_at':AT,'metadata':{'private_body':'never expose'}}],
        'recommendations':[{'id':'rec','organization_id':ORG,'execution_service':'domain_merchant','status':'RECOMMENDED','created_at':AT}],
        'recommendation_evidence':[{'organization_id':ORG,'recommendation_id':'rec','intelligence_report_id':'report'}],
        'execution_requests':[{'id':'request','organization_id':ORG,'recommendation_id':'rec'}],
        'execution_results':[{'id':'result','organization_id':ORG,'execution_request_id':'request'}]}}


def test_stored_records_and_links_do_not_claim_network_calls():
    data=shared_state(context(),{'organization_ids':[ORG]},[])
    assert data['total_records']==4 and data['total_links']==3
    assert data['workflow_records']==0
    assert data['workflow_storage']=='Local orchestrator SQLite'
    assert next(e for e in data['engines'] if e['engine_id']=='decision_engine')['linked_inputs']==1
    assert 'private_body' not in str(data) and 'never expose' not in str(data)
    assert all('API-call timing is not recorded' in l['evidence'] for l in data['links'])


def test_references_require_both_same_tenant_records():
    ctx=context()
    ctx[ORG]['intelligence_reports'][0]['organization_id']=OTHER
    data=shared_state(ctx,{'organization_ids':[ORG]},[])
    assert all(l['from_id']!='report' for l in data['links'])
    assert all(r['id']!='report' for r in data['records'])
    assert shared_state(ctx,{'organization_ids':[OTHER]},[])['total_records']==0
    assert shared_state(ctx,{'organization_ids':[OTHER]},[])['organizations_loaded']==0


def test_missing_context_is_unverified_not_zero_writes():
    data=shared_state({}, {'organization_ids':[ORG]}, [])
    assert all(e['stored_records'] is None for e in data['engines'])
    assert data['organizations_loaded']==0 and data['organizations_configured']==1


def test_log_evidence_does_not_invent_workflow_or_time():
    p={'process_id':'decision:one:domain','process_type':'domain','source':'decision_log','organization_id':ORG,
       'status':'UNKNOWN','stages':[],'reason':'Engine log entry'}
    run,events=normalize([p],{})
    projected=project(run[0],events,{})
    assert projected['workflow_run_id'] is None and projected['last_activity'] is None
    assert projected['evidence_source']['kind']=='engine_log'
    assert provenance({'source':'crm','source_run_id':'crm-report:one'})['label']=='Stored research report'

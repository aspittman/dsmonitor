import json
from pathlib import Path
from adapters.capabilities import from_file
from adapters.trace_events import collect
from adapters.base import timestamp
from services.trace_service import overview, project
from scripts.domain_daily import job_environment


def test_file_scope_and_normalization(tmp_path):
    path=tmp_path/'cap.json'
    config={'capability_files':{'mmonolith':str(path)}}
    path.write_text(json.dumps({'engine_id':'wrong','service_capabilities':{}}))
    assert from_file('mmonolith',config)[1]
    path.write_text(json.dumps({'engine_id':'mmonolith','service_capabilities':{'domain_merchant':{'checked_at':1800000000,'connectivity_status':'CONNECTED','reads':{'execution_results':{'status':'VERIFIED'}}}}}))
    result,error=from_file('mmonolith',config)
    assert not error and result['domain_merchant']['reads']['execution_results']['status']=='VERIFIED'
    path.write_text(' ' * 256001)
    assert from_file('mmonolith',config)[1]


def test_uncorrelated_artifact_receipts_never_invent_workflow(tmp_path):
    path=tmp_path/'mmonolith/logs/capability_events.jsonl';path.parent.mkdir(parents=True)
    row={'engine_id':'mmonolith','service_id':'domain_merchant','organization_id':'org','workflow_run_id':None,
         'trace_event_id':'receipt','stage':'persistence','event_type':'write_persisted','status':'COMPLETED',
         'timestamp':timestamp(1800000000),'source_reference':'intelligence_reports:report','metadata':{'table':'intelligence_reports','record_id':'report'}}
    path.write_text(json.dumps(row)+'\n')
    runs,events,issues=collect({'projects':str(tmp_path),'organization_ids':['org']})
    assert not issues and len(runs)==1 and runs[0]['workflow_run_id'] is None and not runs[0]['expected_path']
    r=project(runs[0],events,{},now=1800000000)
    assert r['stages']==[] and r['status']=='UNKNOWN'
    o=overview([r],{},now=1800000000)
    assert o['summary']['observed_runs']==0
    assert o['pipelines']['domain_merchant'][0]['status']=='CONFIRMED'
    assert collect({'projects':str(tmp_path),'organization_ids':['other']})[0]==[]


def test_daily_environment_precedence_unchanged(tmp_path,monkeypatch):
    for repo in ('mmonolith','decision_engine','devspace-one'):(tmp_path/repo).mkdir()
    (tmp_path/'devspace-one/.env').write_text('CRM_BASE_URL=https://crm.invalid\nCRM_BOT_API_SECRET=test-secret\n')
    (tmp_path/'decision_engine/.env').write_text('LOG_LEVEL=DEBUG\n')
    for key in ('CRM_BASE_URL','CRM_API_URL','BOT_API_SECRET','CRM_API_SECRET','CRM_BOT_API_SECRET'):monkeypatch.delenv(key,raising=False)
    env=job_environment(tmp_path)
    assert env['CRM_API_URL']==env['CRM_BASE_URL']=='https://crm.invalid'
    assert env['CRM_API_SECRET']==env['BOT_API_SECRET']=='test-secret'


def test_diagnostic_unverified_does_not_erase_real_write_evidence():
    from test_service_health import fixture, cell
    cfg,eng,ctx=fixture()
    eng[0]['service_capabilities']['domain_merchant']['write_status']='UNVERIFIED'
    assert cell(cfg,eng,ctx)['write_status']=='VERIFIED'

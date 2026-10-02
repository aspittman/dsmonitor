import json
from services.domain_diagnostic import assess, recent_reports
from scripts.domain_diagnostic import run_cycle


def successful_stages():
    return {
        'research': {'ok': True, 'result': {'candidate_count': 1, 'reported_sales': 5, 'intelligence_report_id': 'r1', 'crm_readback': True}},
        'decision': {'ok': True, 'result': {'consumed_report_ids': ['r1'], 'persisted': True, 'run_id': 'd1', 'summary': {},
            'capabilities': [{'adapter_ready': True, 'status': 'AVAILABLE', 'allowed_actions': ['review_domain_evidence']}]}},
        'readiness': {'ok': True, 'result': {'connectivity_status': 'CONNECTED', 'reads': {'execution_requests': {'status': 'VERIFIED'}}}},
    }


def test_exact_lineage_required():
    stages = successful_stages()
    assert assess({'stages': stages})['status'] == 'READY_FOR_APPROVED_REVIEW'
    stages['decision']['result']['consumed_report_ids'] = ['unrelated']
    report = assess({'stages': stages})
    assert report['status'] == 'BLOCKED'
    assert any(c['stage'] == 'report_consumption' for c in report['gaps'])


def test_policy_rejection_is_not_crash():
    stages = successful_stages()
    stages['decision']['result']['summary'] = {'strategy_decisions': [{'service_id': 'domain_merchant', 'type': 'DOMAIN_ACQUISITION', 'blocking_reasons': ['Missing buyer evidence']}]}
    report = assess({'stages': stages})
    assert report['status'] == 'BLOCKED'
    assert report['gaps'][0]['status'] == 'POLICY_BLOCKED'
    stages['research'] = {'ok': False, 'error_type': 'Timeout'}
    assert assess({'stages': stages})['status'] == 'FAILED'


def test_empty_reads_and_no_candidates_not_healthy():
    stages = successful_stages()
    stages['research']['result']['candidate_count'] = 0
    stages['readiness']['result']['reads'] = {}
    report = assess({'stages': stages})
    assert {'MISSING_INPUT', 'UNVERIFIED'} <= {g['status'] for g in report['gaps']}


def test_reports_scoped_and_corruption_isolated(tmp_path):
    (tmp_path/'one.json').write_text(json.dumps({'organization_id': 'one'}))
    (tmp_path/'two.json').write_text(json.dumps({'organization_id': 'two'}))
    (tmp_path/'bad.json').write_text('{')
    assert recent_reports(tmp_path, ['one']) == [{'organization_id': 'one'}]


def test_cycle_correlates_stages_and_does_not_execute(tmp_path, monkeypatch):
    calls = []
    stages = successful_stages()
    def invoke(base, repo, request, environment, timeout):
        calls.append((repo, request))
        return stages[request['stage']]
    monkeypatch.setattr('scripts.domain_diagnostic.invoke', invoke)
    monkeypatch.setattr('scripts.domain_diagnostic.job_environment', lambda base: {})
    settings = {'projects': str(tmp_path), 'diagnostic_dir': str(tmp_path/'reports')}
    report, path = run_cycle(settings, 'org', {'niche': 'loans', 'keywords': ['loan']})
    assert [r for r, _ in calls] == ['mmonolith', 'decision_engine', 'devspace-one']
    assert {r['context']['workflow_run_id'] for _, r in calls} == {report['workflow_run_id']}
    assert '--namebio-live' in calls[0][1]['args']
    assert '--with-keywords' not in calls[0][1]['args']
    assert json.loads(path.read_text())['status'] == 'READY_FOR_APPROVED_REVIEW'


def test_failed_research_skips_decision_but_checks_readiness(tmp_path, monkeypatch):
    calls = []
    def invoke(base, repo, request, environment, timeout):
        calls.append(request['stage'])
        return {'ok': False, 'error_type': 'Unavailable'}
    monkeypatch.setattr('scripts.domain_diagnostic.invoke', invoke)
    monkeypatch.setattr('scripts.domain_diagnostic.job_environment', lambda base: {})
    report, _ = run_cycle({'projects': str(tmp_path), 'diagnostic_dir': str(tmp_path/'reports')}, 'org', {'niche': 'loans', 'keywords': ['loan']})
    assert calls == ['research', 'readiness']
    assert report['status'] == 'FAILED'


def test_api_filters_tenants_sanitizes_and_remains_readonly(tmp_path):
    from app import create_app
    from config import load_config
    settings = load_config()
    settings.update(database=str(tmp_path/'monitor.db'), diagnostic_dir=str(tmp_path), organization_ids=['one'], secrets=['private-value'])
    (tmp_path/'one.json').write_text(json.dumps({'organization_id': 'one', 'evidence': 'private-value'}))
    (tmp_path/'two.json').write_text(json.dumps({'organization_id': 'two'}))
    with create_app(settings, start_collector=False).test_client() as client:
        response = client.get('/api/diagnostics')
        assert response.status_code == 200
        assert response.json == [{'organization_id': 'one', 'evidence': '[REDACTED]'}]
        assert client.post('/api/diagnostics').status_code == 405
        assert client.get('/api/diagnostics', headers={'Host': 'evil.example'}).status_code == 403


def test_oversize_probe_has_specific_repair_action():
    stages = successful_stages()
    stages['readiness']['result'] = {'connectivity_status': 'UNKNOWN', 'reads': {'execution_requests': {'status': 'UNKNOWN', 'reason': 'Read response exceeds 4 MB safety limit'}}}
    gap = next(g for g in assess({'stages': stages})['gaps'] if g['stage'] == 'execution_read_access')
    assert 'bounded CRM monitoring-capabilities' in gap['next_action']


def test_missing_candidate_evidence_gets_specific_actions():
    stages = successful_stages()
    stages['decision']['result']['summary'] = {'domain_candidate_decisions': [{'checks': {'search_demand': False, 'potential_buyers': False}}]}
    gaps = assess({'stages': stages})['gaps']
    assert {g['stage'] for g in gaps} == {'search_demand', 'potential_buyers'}
    assert all(g['status'] == 'MISSING_INPUT' for g in gaps)

from service_registry import registry
from services.trace_service import overview
from services.service_health import scoped_records


def test_clients_register_real_engines_without_claiming_orchestration():
    spec = registry({})['devspace_clients']
    assert spec['configured'] is True
    assert set(spec['engines']) == {'mmonolith', 'decision_engine', 'crm', 'devspace_one'}
    assert 'coordinator' not in spec
    assert spec['engines']['mmonolith']['outputs'] == ['intelligence_reports']
    assert spec['engines']['mmonolith']['dependencies'] == ['supabase']
    assert not any(edge['consumer_table'] == 'feedback_evaluations' for edge in spec['handoffs'] if 'consumer_table' in edge)


def test_clients_without_evidence_are_unknown_not_healthy_or_unconfigured():
    result = overview([], {}, now=1700000000)
    cells = {c['engine_id']: c for c in result['matrix'] if c['service_id'] == 'devspace_clients'}
    for engine in ('mmonolith', 'decision_engine', 'crm', 'devspace_one'):
        assert cells[engine]['status'] == 'UNKNOWN'
    assert cells['dsorchestrator']['status'] == 'NOT_CONFIGURED'


def test_client_report_stays_separate_from_outreach_ingestion():
    contexts = {'org': {'intelligence_reports': [
        {'id': 'report', 'organization_id': 'org', 'service_id': 'devspace_clients'}],
        'execution_requests': [{'id': 'outreach', 'organization_id': 'org', 'execution_service': 'devspace_outreach'}]}}
    records = scoped_records(contexts, registry({}))
    assert {r['id']: r['service_id'] for r in records} == {
        'report': 'devspace_clients', 'outreach': 'devspace_services'}

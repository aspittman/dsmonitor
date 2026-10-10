import pytest
from scripts.capability_probe import probe

ORG = '11111111-1111-4111-8111-111111111111'


@pytest.mark.parametrize('service', ['devspace_services', 'devspace_clients', 'scholarship_research', 'investor_research'])
def test_orchestrator_requires_shared_persistence_for_linked_research(service, monkeypatch):
    monkeypatch.setattr('scripts.capability_probe.state_reads', lambda *args: {})
    profile = {'engine_id': 'dsorchestrator', 'url_env': 'URL', 'secret_env': 'SECRET',
               'services': {service: {'inputs': ['intelligence_reports']}}}
    def get(*args):
        return {'success': True, 'data': {'organization_id': ORG, 'engine_id': 'dsorchestrator',
            'service_id': service, 'connectivity_status': 'CONNECTED',
            'reads': {'intelligence_reports': {'status': 'VERIFIED'}},
            'configuration': {'verified': True, 'service_enabled': True}}}
    env = {'URL': 'https://crm.example', 'SECRET': 'test'}
    result = probe(profile, [ORG], env, get=get)['service_capabilities'][service]
    assert result['configuration_status'] == 'BLOCKED'
    assert 'SUPABASE_DB_URL' in result['next_action']
    env['SUPABASE_DB_URL'] = 'postgresql://configured'
    assert probe(profile, [ORG], env, get=get)['service_capabilities'][service]['configuration_status'] == 'VERIFIED'

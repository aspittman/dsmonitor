import pytest
from service_registry import registry
from services.trace_service import overview


@pytest.mark.parametrize('service', ['scholarship_research', 'investor_research'])
def test_product_services_register_coordinator_without_fabricating_readiness(service):
    spec = registry({})[service]
    assert spec['coordinator'] == 'dsorchestrator'
    assert set(spec['engines']) == {'mmonolith', 'decision_engine', 'crm', 'dsorchestrator'}
    assert [(stage['stage'], stage['engine_id']) for stage in spec['stages']] == [('research','mmonolith'), ('decision','decision_engine')]
    cells = {cell['engine_id']: cell for cell in overview([], {}, now=1700000000)['matrix'] if cell['service_id'] == service}
    assert cells['dsorchestrator']['status'] == 'UNKNOWN'
    assert cells['devspace_one']['status'] == 'NOT_CONFIGURED'

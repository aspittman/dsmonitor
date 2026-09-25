"""Monitoring expectations, not operational routing. Override with trace_registry JSON."""
from copy import deepcopy

ENGINES = ['mmonolith', 'decision_engine', 'crm', 'dsorchestrator', 'devspace_one']
DOMAIN = [{'stage': name, 'engine_id': engine} for name, engine in (
    ('research', 'mmonolith'), ('decision', 'decision_engine'), ('approval', 'crm'),
    ('execution', 'devspace_one'), ('feedback', 'mmonolith'),
    ('updated_intelligence', 'mmonolith'), ('redecision', 'decision_engine'))]
DEFAULTS = {
    'domain_merchant': {'aliases': ['domain'], 'configured': True, 'stages': DOMAIN,
        'coordinator': 'dsorchestrator', 'note': 'Seven-stage orchestrator domain contract. Direct CRM runs may cover only a subset.'},
    'scholarship_research': {'aliases': ['scholarship', 'scholorship_research'], 'configured': False, 'stages': [],
        'note': 'Neither research spelling exists in the inspected engine configuration. Schopath Scout is separate; no implemented DevSpace path.'},
    'devspace_services': {'aliases': ['devspace-services'], 'configured': False, 'stages': [],
        'note': 'Orchestrator lifecycle declared but business adapters not implemented. DevSpace One outreach is a separate observed capability.'},
    'devspace_clients': {'aliases': ['crm_business', 'crm-companies'], 'configured': False, 'stages': [],
        'note': 'crm-companies lifecycle declared; business adapters not implemented.'},
    'investor_research': {'aliases': [], 'configured': False, 'stages': [], 'note': 'Future service; not configured.'},
}


def registry(config):
    result = deepcopy(DEFAULTS)
    for key, value in config.get('trace_registry', {}).items():
        result[key] = value
    return result


def identify(value, definitions):
    return next((key for key, spec in definitions.items() if value == key or value in spec.get('aliases', [])), value)

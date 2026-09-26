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

# Inspected shared-loop ownership (CRM migrations 014–019 and engine clients).
# These are monitoring contracts, not permission grants or schedules.
DEFAULTS['domain_merchant']['engines'] = {
    'mmonolith': {'inputs': ['execution_results', 'intelligence_reports'],
                 'outputs': ['intelligence_reports', 'feedback_evaluations'], 'dependencies': ['crm']},
    'decision_engine': {'inputs': ['market_signals', 'intelligence_reports', 'predictions'],
                        'outputs': ['recommendations'], 'dependencies': ['crm']},
    'crm': {'inputs': ['intelligence_reports', 'recommendations', 'execution_requests', 'execution_results'],
            'outputs': ['execution_requests'], 'dependencies': ['supabase']},
    'devspace_one': {'inputs': ['execution_requests'], 'outputs': ['execution_results'], 'dependencies': ['crm']},
    'dsorchestrator': {'inputs': ['workflow_runs', 'stage_runs'], 'outputs': ['stage_runs'], 'dependencies': ['crm']},
}
DEFAULTS['domain_merchant']['handoffs'] = [
    {'id': 'intelligence_write', 'from': 'mmonolith', 'to': 'crm', 'table': 'intelligence_reports'},
    {'id': 'intelligence_read', 'from': 'crm', 'to': 'decision_engine', 'table': 'intelligence_reports',
     'consumer_table': 'recommendation_evidence', 'foreign_key': 'intelligence_report_id'},
    {'id': 'recommendation_write', 'from': 'decision_engine', 'to': 'crm', 'table': 'recommendations'},
    {'id': 'request_consumption', 'from': 'crm', 'to': 'devspace_one', 'table': 'execution_requests',
     'consumer_table': 'execution_results', 'foreign_key': 'execution_request_id', 'approval_required': True,
     'receipt_statuses': ['RUNNING', 'COMPLETED'], 'receipt_timestamp': 'updated_at'},
    {'id': 'result_write', 'from': 'devspace_one', 'to': 'crm', 'table': 'execution_results'},
    {'id': 'feedback_read', 'from': 'crm', 'to': 'mmonolith', 'table': 'execution_results',
     'consumer_table': 'feedback_evaluations', 'foreign_key': 'execution_result_id'},
]
for edge, stage in zip(DEFAULTS['domain_merchant']['handoffs'],
                       ('research', 'decision', 'decision', 'execution', 'execution', 'feedback')):
    edge['stage'] = stage
# Existing process_service attribution and devspace-one/services/devspace_outreach
# establish this partial participation, not an implemented orchestrator lifecycle.
DEFAULTS['devspace_services'].update(configured=True,
    engines={'crm': {'inputs': ['leads', 'companies', 'contacts'],
                     'outputs': ['leads', 'companies', 'contacts'], 'dependencies': ['supabase']},
             'devspace_one': {'inputs': ['leads'], 'outputs': ['leads'],
                              'dependencies': ['crm']}},
    handoffs=[{'id': 'outreach_ingestion', 'from': 'devspace_one', 'to': 'crm', 'table': 'leads'}],
    note='Partial CRM / DevSpace One outreach participation: domain-exists reads leads; /api/ingest persists companies, contacts and leads. Existing loop context does not expose these legacy receipts. The declared cross-engine lifecycle has no real business adapters.')


def registry(config):
    result = deepcopy(DEFAULTS)
    for key, value in config.get('trace_registry', {}).items():
        result[key] = value
    return result


def identify(value, definitions):
    return next((key for key, spec in definitions.items() if value == key or value in spec.get('aliases', [])), value)

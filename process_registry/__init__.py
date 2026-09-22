"""Registration affects labels/aliases only; stages always come from source records."""
REGISTRY = {}


def register_process(id, display_name, aliases=(), note=''):
    REGISTRY[id] = {'id': id, 'display_name': display_name, 'aliases': list(aliases), 'note': note}


def identify(value):
    return next((k for k, v in REGISTRY.items() if value == k or value in v['aliases']), value)


register_process('domain', 'Domain', note='Orchestrator domain lifecycle and ID-linked CRM evidence')
register_process('scholarship', 'Scholarship App', note='NOT CONFIGURED: Schopath Scout is separate; no DevSpace integration exists')
register_process('devspace_services', 'DevSpace Services / Outreach', ['devspace-services'], 'Discovery, audits and drafts exist in DevSpace One; orchestrator adapters are not implemented')
register_process('crm_business', 'CRM Businesses / Clients', ['crm-companies'], 'Organization-scoped orchestration; engine adapters are not implemented')

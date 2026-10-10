"""Registration affects labels/aliases only; stages always come from source records."""
REGISTRY = {}


def register_process(id, display_name, aliases=(), note=''):
    REGISTRY[id] = {'id': id, 'display_name': display_name, 'aliases': list(aliases), 'note': note}


def identify(value):
    return next((k for k, v in REGISTRY.items() if value == k or value in v['aliases']), value)


register_process('domain', 'Domain', note='Orchestrator domain lifecycle and ID-linked CRM evidence')
register_process('scholarship', 'Schopath / Scholarship Research', ['scholarship_research', 'scholorship_research'], 'Backend research and profile matching have local orchestrator adapters; app data transport is separate')
register_process('investor_research', 'Investorpath / Investor Research', note='Backend research and profile matching have local orchestrator adapters; app data transport is separate')
register_process('devspace_services', 'DevSpace Services / Outreach', ['devspace-services'], 'Research and advisory decisions have local orchestrator adapters; outreach ingestion remains a separate DevSpace One path')
register_process('crm_business', 'CRM Businesses / Clients', ['crm-companies'], 'Organization-scoped research and advisory orchestration; approved draft preparation remains a separate worker')

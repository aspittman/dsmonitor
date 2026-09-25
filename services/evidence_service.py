"""Explain observations without promoting logs or stored rows into workflow receipts."""
from adapters.base import timestamp
from service_registry import identify, registry

# Ownership describes the contract, not an authenticated per-request caller audit.
TABLES = {
    'market_signals': ('mmonolith', 'Market signal'),
    'intelligence_reports': ('mmonolith', 'Research report'),
    'predictions': ('mmonolith', 'Prediction'),
    'recommendations': ('decision_engine', 'Recommendation'),
    'execution_requests': ('crm', 'Execution request'),
    'execution_results': ('devspace_one', 'Execution result'),
    'feedback_evaluations': ('mmonolith', 'Feedback evaluation'),
}


def provenance(record):
    source = record.get('source')
    rid = record.get('source_run_id') or record.get('process_id') or ''
    if source == 'dsorchestrator':
        return {'kind':'workflow', 'label':'Orchestrator workflow', 'location':'workflow_runs + stage_runs',
                'meaning':'The coordinator recorded this workflow and its stage state. Referenced CRM records are verified separately.'}
    if source == 'crm':
        report = str(rid).startswith('crm-report:')
        return {'kind':'crm_record', 'label':'Stored research report' if report else 'CRM recommendation records',
                'location':'CRM API → intelligence_reports' if report else 'CRM API → recommendations and linked records',
                'meaning':'Read back from CRM/Supabase. Record existence is verified; a complete workflow or downstream read is not implied.'}
    if source == 'decision_log':
        return {'kind':'engine_log','label':'Decision Engine log', 'location':'Configured decision log → decision_completed',
                'meaning':'The engine logged an evaluation. This row alone does not verify a CRM write, downstream receipt, or full workflow.'}
    return {'kind':'source_events','label':'Source trace events','location':'Configured engine trace file',
            'meaning':'Events reported by source instrumentation; CRM persistence requires separately verified records.'}


def shared_state(contexts, config, processes):
    contexts={org:ctx for org,ctx in contexts.items() if org in config.get('organization_ids',[])}
    records, links = [], []
    definitions = registry(config)
    for org, context in contexts.items():
        if org not in config.get('organization_ids', []): continue
        index = {table:{r['id']:r for r in context.get(table, []) if r.get('organization_id')==org and r.get('id')}
                 for table in TABLES}
        edges = set()
        def link(source_table, source_id, target_table, target_id, description):
            if not source_id or not target_id: return
            if source_id not in index.get(source_table,{}) or target_id not in index.get(target_table,{}): return
            key=(source_table,source_id,target_table,target_id)
            if key in edges: return
            edges.add(key)
            links.append({'organization_id':org,'from_table':source_table,'from_id':source_id,
                          'to_table':target_table,'to_id':target_id,'description':description,
                          'reader_engine':TABLES[target_table][0], 'evidence':'Both records and an explicit reference were read from CRM; API-call timing is not recorded here.'})
        for row in context.get('recommendation_evidence',[]):
            if row.get('organization_id')!=org: continue
            for field,table in [('intelligence_report_id','intelligence_reports'),('signal_id','market_signals'),('execution_result_id','execution_results')]:
                link(table,row.get(field),'recommendations',row.get('recommendation_id'),'Recommendation cites this evidence')
        for table, source_table, field, text in [
            ('predictions','intelligence_reports','intelligence_report_id','Prediction references this research'),
            ('execution_requests','recommendations','recommendation_id','Request references this recommendation'),
            ('execution_results','execution_requests','execution_request_id','Result references this execution request'),
            ('feedback_evaluations','execution_results','execution_result_id','Feedback references this result'),
            ('feedback_evaluations','predictions','prediction_id','Feedback evaluates this prediction'),
        ]:
            for row in index[table].values(): link(source_table,row.get(field),table,row['id'],text)
        for row in context.get('intelligence_report_feedback',[]):
            if row.get('organization_id')==org:
                link('feedback_evaluations',row.get('feedback_id'),'intelligence_reports',row.get('report_id'),'New research cites this feedback')
        for table, rows in index.items():
            owner, concept = TABLES[table]
            for rid, row in rows.items():
                metadata=row.get('metadata') if isinstance(row.get('metadata'),dict) else {}
                workflow=metadata.get('workflow_context') if isinstance(metadata.get('workflow_context'),dict) else {}
                service=row.get('service_id') or workflow.get('service_id')
                if not service and (row.get('report_type')=='DOMAIN_MARKET' or row.get('execution_service')=='domain_merchant'):
                    service='domain_merchant'
                service=identify(service,definitions) if service else None
                records.append({'id':rid,'table':table,'concept':concept,'organization_id':org,
                    'owner_engine':owner,'service_id':service,'workflow_run_id':row.get('workflow_run_id') or workflow.get('workflow_run_id'),
                    'status':row.get('status') or row.get('evaluation'),
                    'created_at':timestamp(row.get('created_at')),'completed_at':timestamp(row.get('completed_at')),
                    'observed_at':context.get('_observed_at'),
                    'meaning':'Stored row verified by CRM read-back; not a captured request payload or proof of every consumer read.'})
    records.sort(key=lambda r:r['created_at'] or '',reverse=True)
    engines=[]
    for engine in ('mmonolith','decision_engine','crm','devspace_one'):
        owned=[r for r in records if r['owner_engine']==engine]
        engines.append({'engine_id':engine,'tables':[t for t,(owner,_) in TABLES.items() if owner==engine],
                        'stored_records':len(owned) if contexts else None,
                        'linked_inputs':sum(e['reader_engine']==engine for e in links) if contexts else None,
                        'last_record_at':max((r['created_at'] for r in owned if r['created_at']),default=None)})
    return {'records':records[:200], 'links':links[:200], 'engines':engines,
            'total_records':len(records),'total_links':len(links),'limited':len(records)>200 or len(links)>200,
            'organizations_loaded':len(contexts),'organizations_configured':len(config.get('organization_ids',[])),
            'observed_at':min((c['_observed_at'] for c in contexts.values() if c.get('_observed_at')),default=None),
            'workflow_records':sum(p.get('source')=='dsorchestrator' for p in processes),
            'workflow_storage':'Shared PostgreSQL' if config.get('orchestrator_dsn') else 'Local orchestrator SQLite',
            'read_api_paths':['GET /api/decision-engine/context','GET /api/bot/feedback-loop/context'],
            'limitation':'These are stored records and explicit reference links. Per-engine HTTP/SQL reads, attempted writes and request latency are not captured by these sources.'}

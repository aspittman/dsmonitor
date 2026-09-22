"""Resolve only explicit reference IDs inside one validated organization."""
from adapters.base import timestamp

TABLES = {'intelligence_report':'intelligence_reports','recommendation':'recommendations','execution_request':'execution_requests',
          'execution_result':'execution_results','feedback_evaluation':'feedback_evaluations','prediction':'predictions'}
LINKS = {'intelligence_report_id':'intelligence_reports', 'previous_report_id':'intelligence_reports', 'recommendation_id':'recommendations',
         'execution_request_id':'execution_requests','execution_result_id':'execution_results','prediction_id':'predictions',
         'feedback_id':'feedback_evaluations','report_id':'intelligence_reports','decision_run_id':'decision_runs'}


def enrich(processes, contexts):
    for process in processes:
        context = contexts.get(process['organization_id'], {})
        index = {table:{r['id']:r for r in rows if r.get('organization_id') == process['organization_id']}
                 for table, rows in context.items() if isinstance(rows, list) and table != 'execution_capabilities'}
        pending = []
        for stage in process['stages']:
            for refs in stage.get('references', {}).values():
                for key, ids in refs.items():
                    table = TABLES.get(key.removesuffix('_ids').removesuffix('_id'))
                    if table:
                        for rid in ids if isinstance(ids,list) else [ids]: pending.append((table,rid,'stage '+stage['stage']))
        seen, nodes = set(), []
        while pending and len(seen) < 500:
            table, rid, via = pending.pop(0)
            if (table,rid) in seen: continue
            seen.add((table,rid))
            row = index.get(table,{}).get(rid)
            node = {'table':table,'id':rid,'via':via,'verified':bool(row),'status':row.get('status') if row else 'UNVERIFIED',
                    'timestamp':timestamp(row.get('completed_at') or row.get('created_at')) if row else None,
                    'is_test':row.get('is_test') if row else None, 'observed_at':context.get('_observed_at')}
            nodes.append(node)
            if row:
                for field, target in LINKS.items():
                    if row.get(field): pending.append((target,row[field],f'{table}.{field}'))
        process['lineage'] = nodes
    return processes

"""CRM-only traces for recommendations not already attributed to an orchestrator run."""
from dataclasses import asdict
from adapters.base import timestamp, epoch
from models import ProcessStatus, StageStatus


def crm_processes(contexts, tracked):
    linked=set()
    for p in tracked:
        for s in p['stages']:
            for refs in s.get('references',{}).values():
                for key in ('recommendation_ids','recommendation_id'):
                    ids=refs.get(key,[])
                    linked.update((p['organization_id'],rid) for rid in (ids if isinstance(ids,list) else [ids]))
    result=[]
    for org,ctx in contexts.items():
        reports={r['id']:r for r in ctx.get('intelligence_reports',[])}
        for rec in ctx.get('recommendations',[]):
            if (org,rec['id']) in linked: continue
            kind='domain' if rec['recommendation_type'].startswith('DOMAIN_') else 'devspace_services' if rec.get('execution_service') in ('devspace_outreach','apollo_outreach') else rec.get('execution_service') or 'unknown_service'
            p=ProcessStatus('crm:'+rec['id'],kind,'Recommendation · '+rec['recommendation_type'],rec['status'],organization_id=org,
                            current_stage='decision',started_at=timestamp(rec['created_at']),last_activity=timestamp(rec.get('updated_at')),source='crm')
            p.source_status=rec['status']
            p.reason='CRM recommendation lifecycle, not a full orchestrator run. Only explicitly linked records appear. Context observed: ' + str(ctx.get('_observed_at','unknown'))
            def add(stage,engine,status,row,refs,at=None):
                completed=timestamp(at or row.get('completed_at') or row.get('created_at'))
                start=timestamp(row.get('started_at'))
                elapsed=epoch(completed)-epoch(start) if start and completed else None
                p.stages.append(asdict(StageStatus(stage,engine,status,start,completed,elapsed,None,row.get('error_message'),{'output':refs})))
                if completed and (not p.last_activity or completed>p.last_activity):p.last_activity=completed
            for evidence in ctx.get('recommendation_evidence',[]):
                if evidence.get('recommendation_id')==rec['id'] and evidence.get('intelligence_report_id') in reports:
                    report=reports[evidence['intelligence_report_id']]
                    add('research','mmonolith','COMPLETED',report,{'intelligence_report_id':report['id']})
                    p.correlation_id=report.get('correlation_id')
            add('decision','decision_engine','COMPLETED',rec,{'recommendation_id':rec['id']})
            requests=[r for r in ctx.get('execution_requests',[]) if r['recommendation_id']==rec['id']]
            for req in requests:
                if req.get('approved_at') and req.get('approved_by'):
                    add('approval','crm','COMPLETED',req,{'execution_request_id':req['id']},req['approved_at'])
                    p.current_stage='execution'
                executions=[r for r in ctx.get('execution_results',[]) if r['execution_request_id']==req['id']]
                for execution in executions:
                    add('execution','devspace_one',execution['status'],execution,{'execution_result_id':execution['id']})
                    for feedback in ctx.get('feedback_evaluations',[]):
                        if feedback['execution_result_id']==execution['id'] and feedback['recommendation_id']==rec['id']:
                            add('feedback','mmonolith','COMPLETED',feedback,{'feedback_evaluation_id':feedback['id']})
                            p.current_stage='feedback'
                            for edge in ctx.get('intelligence_report_feedback',[]):
                                if edge['feedback_id']==feedback['id'] and edge['report_id'] in reports:
                                    report=reports[edge['report_id']]
                                    add('updated_intelligence','mmonolith','COMPLETED',report,{'intelligence_report_id':report['id']})
                                    p.current_stage='updated_intelligence'
                if not executions:
                    p.stages.append(asdict(StageStatus('execution','devspace_one',req['status'],references={'input':{'execution_request_id':req['id']}})))
            if rec['recommendation_type']=='NO_ACTION':
                p.status='SKIPPED'; p.current_stage='decision'
                p.reason='Explicit NO_ACTION recommendation; no execution or approval is expected.'
            elif not requests and rec['status'] == 'RECOMMENDED':
                p.current_stage='approval'; p.status='WAITING_FOR_APPROVAL'
            p.error_count=sum(s['status']=='FAILED' for s in p.stages)
            p.last_error=next((s['error'] for s in reversed(p.stages) if s['error']),None)
            result.append(p.dict())
    # Preserve structured research without recommendations. A stored report is
    # source evidence, not proof that a decision engine received it.
    linked_reports=set()
    for p in tracked+result:
        for s in p['stages']:
            for refs in s.get('references',{}).values():
                ids=refs.get('intelligence_report_ids',refs.get('intelligence_report_id',[]))
                linked_reports.update((p['organization_id'],rid) for rid in (ids if isinstance(ids,list) else [ids]))
    for org,ctx in contexts.items():
        for report in ctx.get('intelligence_reports',[]):
            if (org,report['id']) in linked_reports: continue
            kind='domain' if report.get('report_type')=='DOMAIN_MARKET' else report.get('service_id') or 'unknown_service'
            at=timestamp(report.get('created_at'))
            p=ProcessStatus('crm-report:'+report['id'],kind,'Research report', 'UNKNOWN',organization_id=org,
                last_activity=at,correlation_id=report.get('correlation_id'),source='crm',
                reason='Stored research report; downstream receipt and workflow completion are unverified.')
            p.stages=[asdict(StageStatus('research','mmonolith','COMPLETED',completed_at=at,
                references={'output':{'intelligence_report_id':report['id']}}))]
            result.append(p.dict())
    return result


def crm_activity(contexts):
    rows=[]
    for org,ctx in contexts.items():
        for table,engine,event in [('intelligence_reports','mmonolith','Intelligence report stored'),('recommendations','decision_engine','Recommendation created'),('execution_results','devspace_one','Execution result stored'),('feedback_evaluations','mmonolith','Feedback evaluation stored')]:
            for r in ctx.get(table,[]):
                at=timestamp(r.get('completed_at') or r.get('created_at'))
                if not at:continue
                rows.append({'id':table+':'+r['id'],'timestamp':at,'engine':engine,'status':r.get('status','OBSERVED'),
                             'message':r.get('error_message') or event,'organization_id':org,'process_id':None,'source':table,
                             'process_type':None,'reference_id':r['id']})
    return rows

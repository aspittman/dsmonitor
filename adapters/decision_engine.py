from adapters.local import collect as local_collect

def collect(config):
    return local_collect('decision_engine', config)


def service_runs(config):
    """Read the existing structured daily-job log, preserving missing timestamps.

    Domain attribution uses explicit DOMAIN_ACQUISITION strategy output only.
    A multi-strategy run is not assigned wholesale to a service.
    """
    import json
    from pathlib import Path
    from models import ProcessStatus, StageStatus
    from dataclasses import asdict
    from adapters.base import timestamp
    path=Path(config.get('decision_trace_log') or Path(__file__).resolve().parents[1]/'logs/domain_decide.log')
    if not path.is_file(): return []
    with path.open('rb') as stream:
        stream.seek(0,2)
        size=stream.tell()
        stream.seek(max(0,size-2_000_000))
        if size>2_000_000: stream.readline()
        lines=stream.readlines()[-1000:]
    result={}
    for line in lines:
        try: row=json.loads(line)
        except (ValueError,UnicodeDecodeError): continue
        if not isinstance(row,dict) or row.get('event')!='decision_completed' or not row.get('decision_run_id'): continue
        org=row.get('organization_id')
        if org not in config.get('organization_ids',[]): continue
        reasons=[r for r in row.get('strategies_rejected',[]) if isinstance(r,str) and r.startswith('DOMAIN_ACQUISITION:')]
        failures=[e.get('error_type') for e in row.get('errors',[]) if e.get('strategy')=='DOMAIN_ACQUISITION']
        if not reasons and not failures and not row.get('domain_candidate_decisions'): continue
        at=timestamp(row.get('timestamp'))
        error=', '.join(failures) if failures else None
        p=ProcessStatus('decision:'+row['decision_run_id']+':domain','domain','Domain strategy evaluation',
            'FAILED' if failures else 'UNKNOWN',organization_id=org,last_activity=at,source='decision_log',
            reason='Structured decision strategy evidence. '+(' '.join(reasons) or 'Domain candidates evaluated.')+
                   ' No verified end-to-end lineage. Log occurrence time unavailable.' if not at else 'Structured decision strategy evidence.')
        p.stages=[asdict(StageStatus('decision','decision_engine','FAILED' if failures else 'COMPLETED',
            completed_at=at,error=error,references={}))]
        p.stages[0]['source_reference']=row['decision_run_id']
        result[p.process_id]=p.dict()
    return list(result.values())

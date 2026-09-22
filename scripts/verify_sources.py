"""Read-only source verification. Never starts or modifies a DevSpace workflow."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import load_config
from services.monitor import Monitor


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow', help='Existing workflow/run ID to inspect; performs no execution')
    parser.add_argument('--organization', action='append', default=[], help='Explicit organization UUID to inspect read-only')
    args=parser.parse_args()
    config=load_config()
    if args.organization:
        from uuid import UUID
        config['organization_ids']=[str(UUID(value)) for value in args.organization]
    monitor=Monitor(config)
    data=monitor.collect()
    if args.workflow:
        process=next((p for p in data['processes'] if p['process_id']==args.workflow),None)
        if not process:
            print(json.dumps({'verified':False,'reason':'Run not found in the configured, tenant-scoped source window','coverage':data['coverage']},indent=2))
            return 2
        # No fixed lifecycle is imposed on other workflows.
        verified=process['source']=='dsorchestrator' and process['status']=='COMPLETED' and bool(process['stages']) and all(s['status']=='COMPLETED' for s in process['stages']) and bool(process['lineage']) and all(n['verified'] for n in process['lineage'])
        print(json.dumps({'verified':verified,'meaning':'All recorded stages complete and every referenced record readable within the organization; not proof of external side effects','process':process},indent=2))
        return 0 if verified else 2
    print(json.dumps({'observed_at':data['collected_at'],'engines':[
        {k:e[k] for k in ('engine_id','display_name','status','availability','last_activity','last_success','checks','metrics')}
        for e in data['engines']], 'coverage':data['coverage'],'process_count':len(data['processes']),
        'source_contexts':{org:{table:len(rows) for table,rows in cached[1].items() if isinstance(rows,list)} for org,cached in monitor.crm_cache.items()}, 'observed_errors':len(data['errors']),'monitor_errors':data['monitor_errors'], 'trace_summary':data.get('trace_overview',{}).get('summary'), 'traces':[{'id':r['trace_id'],'source_run_id':r['source_run_id'],'service':r['service_id'],'status':r['status'],'quality':r['correlation_quality'],'stages':[{'engine':s['engine_id'],'stage':s['stage'],'status':s['status']} for s in r['stages']]} for r in data.get('traces',[])]},indent=2))
    return 0


if __name__=='__main__':
    sys.exit(main())

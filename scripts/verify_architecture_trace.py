"""Read-only check of an existing fixture run; never starts or advances engines."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.dsorchestrator import collect
from services.trace_service import normalize, project, overview


def main():
    config = {'orchestrator_dsn':os.environ['ARCHITECTURE_TEST_DSN'],
              'organization_ids':[os.environ['ARCHITECTURE_TEST_ORG']],
              'timeout_seconds':5,'limit':100,'stale_seconds':{}}
    processes, health = collect(config)
    runs, events = normalize(processes, config)
    run = next(r for r in runs if r['workflow_run_id']==os.environ['ARCHITECTURE_TEST_RUN'])
    trace = project(run, events, config)
    assert health['status']=='HEALTHY'
    assert trace['service_id']=='domain_merchant'
    assert trace['status']=='COMPLETED' and not trace['root_failure']
    assert trace['duration_seconds'] is not None
    assert len(trace['stages'])==7
    summary = overview([trace], config)
    assert summary['summary']['completed_today']==1
    print(json.dumps({'monitor_verified':True,'workflow_run_id':run['workflow_run_id'],'stages':len(trace['stages']),'trace_events':len(events)}))


if __name__=='__main__': main()

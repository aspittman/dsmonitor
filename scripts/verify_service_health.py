"""Read-only live verification; temporary SQLite monitoring store, no business writes."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import load_config
from services.monitor import Monitor

if __name__ == '__main__':
    config = load_config()
    with tempfile.TemporaryDirectory(prefix='dsmonitor-health-') as directory:
        config['database'] = str(Path(directory) / 'verification.db')
        data = Monitor(config).collect()
    result = {
        'observed_at': data['collected_at'], 'monitor_errors': data['monitor_errors'],
        'engines': [{'engine_id': e['engine_id'], 'availability': e['availability'], 'checks': e['checks']} for e in data['engines']],
        'cells': [{k:c.get(k) for k in ('service_id','engine_id','status','reason','connectivity_status','read_status','write_status','handoff_status','workflow_status','activity_status','last_write')} for c in data['trace_overview']['matrix']],
        'pipelines': data['trace_overview'].get('pipelines', {}),
        'health_summary': data['trace_overview'].get('health_summary', {}),
        'scope': 'One read-only live collection. Temporary local monitoring history. No engine launched and no business data modified.'
    }
    output = Path(sys.argv[1]) if len(sys.argv)>1 else Path('docs/service-health-validation.json')
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'output':str(output), 'observed_at':result['observed_at'], 'health_summary':result['health_summary'],
                      'monitor_errors':result['monitor_errors'], 'dependency_checks': {e['engine_id']:e['checks'] for e in result['engines'] if e['engine_id'] in ('crm','supabase')},
                      'handoffs':{s:[{'id':e['id'],'status':e['status']} for e in edges] for s,edges in result['pipelines'].items()}}, indent=2))

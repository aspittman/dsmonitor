"""Consume bounded engine-owned reports; never launch an engine from dsmonitor."""
import json
from pathlib import Path
from adapters.base import timestamp


def normalize(reports):
    result={}
    if not isinstance(reports,dict): return result
    for service, report in list(reports.items())[:100]:
        if not isinstance(report,dict): continue
        reads=report.get('reads',{})
        result[service]={
            'checked_at':timestamp(report.get('checked_at')),
            'connectivity_status':report.get('connectivity_status'),
            'configuration_status':report.get('configuration_status', 'UNVERIFIED'),
            'configuration_checks':report.get('configuration_checks', []),
            'next_action':str(report.get('next_action') or 'Check the engine diagnostic publisher and CRM monitoring endpoint.')[:500],
            'write_status':report.get('write_status'), 'last_read':timestamp(report.get('last_read')),
            'last_write':timestamp(report.get('last_write')),
            'work_expected':report.get('work_expected') if isinstance(report.get('work_expected'),bool) else None,
            'organization_ids':[o for o in report.get('organization_ids',[]) if isinstance(o,str)][:20] if isinstance(report.get('organization_ids'),list) else [],
            'reason':str(report.get('reason') or 'Engine-owned capability report')[:500],
            'configuration_scope':str(report.get('configuration_scope') or 'configured health endpoint')[:200],
            'reads':{str(table):{'status':row.get('status'),'reason':str(row.get('reason') or '')[:500]}
                     for table,row in list(reads.items())[:100] if isinstance(row,dict)} if isinstance(reads,dict) else {},
        }
    return result


def from_file(engine, config):
    path=config.get('capability_files',{}).get(engine)
    if not path: return {},None
    try:
        with Path(path).open('rb') as f: raw=f.read(256_001)
        if len(raw)>256_000: raise ValueError('oversized')
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get('engine_id')!=engine: raise ValueError('scope')
        return normalize(data.get('service_capabilities')),None
    except FileNotFoundError:
        return {},'Engine diagnostic report has not been published'
    except Exception:
        return {},'Engine diagnostic report invalid or unreadable; independent monitoring continues'

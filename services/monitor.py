import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from adapters import mmonolith, decision_engine, devspace_one, crm, supabase, dsorchestrator
from adapters.local import collect as local_collect
from models import EngineStatus
from process_registry import REGISTRY, register_process
from services.health_service import explain
from services.security import Sanitizer
from services.snapshot_service import SnapshotStore
from services.workflow_trace_service import enrich
from services.process_service import crm_processes, crm_activity
from services.trace_service import normalize, project, overview
from services.evidence_service import provenance, shared_state


class Monitor:
    def __init__(self, config):
        self.config=config
        self.sanitizer=Sanitizer(config.get('secrets', []))
        try: self.store=SnapshotStore(config['database'], config['retention_days'])
        except Exception: self.store=None
        self.lock=threading.Lock()
        self.stop=threading.Event()
        self.thread=None
        self.last_snapshot=0
        self.crm_cache={}
        self.data={'collected_at':None,'engines':[],'processes':[],'activity':[],'errors':[], 'summary':{}, 'coverage':{}, 'organizations':[], 'registry':list(REGISTRY.values()),'monitor_errors':[]}
        for spec in config.get('extra_processes',[]): register_process(**spec)

    def collect(self):
        jobs={'mmonolith':lambda:mmonolith.collect(self.config), 'decision_engine':lambda:decision_engine.collect(self.config),
              'devspace_one':lambda:devspace_one.collect(self.config), 'dsorchestrator':lambda:local_collect('dsorchestrator',self.config),
              'crm':lambda:crm.collect(self.config,self.crm_cache), 'supabase':lambda:supabase.collect(self.config),
              'workflows':lambda:dsorchestrator.collect(self.config)}
        results={}
        with ThreadPoolExecutor(max_workers=7) as pool:
            futures={pool.submit(job):key for key,job in jobs.items()}
            for future in as_completed(futures):
                key=futures[future]
                try: results[key]=future.result()
                except Exception:
                    if key=='workflows': results[key]=([],{'status':'UNKNOWN','reason':'Workflow state unavailable, unreadable or schema incompatible','complete':False})
                    else:
                        result=EngineStatus(key,{'devspace_one':'DevSpace One','decision_engine':'Decision Engine'}.get(key,key),infrastructure=key in ('crm','supabase')).dict()
                        result['checks']=[{'name':'Adapter','status':'UNKNOWN','reason':'Monitoring adapter failed; other sources continue independently'}]
                        results[key]=(result,{},[]) if key=='crm' else result
        processes, coverage=results['workflows']
        crm_engine, contexts, orgs=results['crm']
        normalization_errors=[]
        try:
            processes += crm_processes(contexts,processes)
            processes=enrich(processes,contexts)
            crm_events=crm_activity(contexts)
        except Exception:
            crm_events=[]
            normalization_errors.append('CRM monitoring records could not be normalized; independent engine and workflow sources remain available')
            crm_engine['status']='UNKNOWN'
            crm_engine['dependency_status']='UNKNOWN'
            crm_engine['monitoring_issue']='CRM records could not be interpreted; operational health is not established'
            crm_engine['checks'].append({'name':'Record normalization','status':'UNKNOWN','reason':'Unexpected monitoring record format'})
        try: processes += decision_engine.service_runs(self.config)
        except Exception: normalization_errors.append('Decision structured log unavailable; other trace sources remain available')
        engines=[results[k] for k in ('mmonolith','decision_engine','devspace_one','dsorchestrator')]+[crm_engine,results['supabase']]
        engines[3]['checks'].append({'name':'Workflow state','status':coverage['status'],'reason':coverage['reason']})
        activity=[a for engine in engines for a in engine['activity']] + crm_events
        errors=[a for engine in engines for a in engine['errors']] + [a for a in activity if a['status']=='FAILED']
        for p in processes:
            for s in p['stages']:
                if not s['completed_at'] and not s['started_at']: continue
                row={'id':p['process_id']+':'+s['stage']+':'+s['status'],'timestamp':s['completed_at'] or s['started_at'],
                     'engine':s['engine'],'status':s['status'],'process_id':p['process_id'],'process_type':p['process_type'],
                     'organization_id':p['organization_id'],'stage':s['stage'],'message':s['error'] or s['stage']+' — '+s['status'],
                     'retries':s['retries'],'source':'stage_runs' if p['source']=='dsorchestrator' else 'crm references'}
                activity.append(row)
                if s['error'] or s['status']=='FAILED': errors.append(row)
            if p['last_error'] and not any(s['error']==p['last_error'] for s in p['stages']):
                errors.append({'id':p['process_id']+':error','timestamp':p['last_activity'],'engine':'dsorchestrator','status':'ERROR','process_id':p['process_id'],'process_type':p['process_type'],'organization_id':p['organization_id'],'stage':p['current_stage'],'message':p['last_error'],'source':'workflow_runs'})
        engines=explain(engines,processes)
        today=datetime.now(timezone.utc).date().isoformat()
        complete=coverage['complete']
        tracked=[p for p in processes if p['source']=='dsorchestrator']
        summary={'engines_online':sum(e['availability']=='ONLINE' for e in engines[:4]),
                 'engines_degraded':sum(e['status']=='DEGRADED' for e in engines[:4]),
                 'active_processes':sum((p.get('source_status') or p['status'])=='RUNNING' for p in tracked) if complete else None,
                 'waiting_for_approval':sum(p['status']=='WAITING_FOR_APPROVAL' for p in tracked) if complete else None,
                 'failed_processes':sum(p['status']=='FAILED' for p in tracked) if complete else None,
                 'completed_today':sum(p['status']=='COMPLETED' and (p['completed_at'] or '').startswith(today) for p in tracked) if complete else None,
                 'errors_today':None}
        data={'collected_at':datetime.now(timezone.utc).isoformat(),'engines':engines,'processes':processes,
              'activity':sorted(activity,key=lambda x:x['timestamp'] or '',reverse=True)[:200],
              'errors':sorted(errors,key=lambda x:x['timestamp'] or '',reverse=True)[:200],
              'summary':summary,'coverage':coverage,'organizations':orgs,'registry':list(REGISTRY.values()),'monitor_errors':normalization_errors}
        for process in processes:
            process['evidence_source']=provenance(process)
        try:
            data['shared_state']=shared_state(contexts,self.config,processes)
        except Exception:
            data['shared_state']={}
            data['monitor_errors'].append('CRM evidence summary unavailable; other observations remain available')
        data=self.sanitizer.clean(data)
        try:
            runs, trace_events = [], []
            for process in data['processes']:
                try:
                    normalized, events = normalize([process], self.config)
                    runs.extend(normalized)
                    trace_events.extend(events)
                except Exception:
                    data['monitor_errors'].append('One source run could not be normalized; other traces remain available')
            from adapters.trace_events import collect as collect_trace_files
            extra_runs, extra_events, issues = collect_trace_files(self.config)
            known={r['trace_id'] for r in runs}
            runs += [r for r in extra_runs if r['trace_id'] not in known]
            trace_events += extra_events
            data['monitor_errors'].extend(issues)
            runs, trace_events = self.sanitizer.clean(runs), self.sanitizer.clean(trace_events)
            try:
                self.store.save_traces(runs, trace_events)
                runs, trace_events = self.store.traces(self.config.get('trace_limit', 1000))
            except Exception:
                data['monitor_errors'].append('Trace history unavailable; displaying current source evidence only')
            runs=[r for r in runs if r['source']=='dsorchestrator' and not self.config.get('orchestrator_dsn') or not r.get('organization_id') or r['organization_id'] in self.config.get('organization_ids',[])]
            grouped = {}
            for event in trace_events:
                grouped.setdefault(event['trace_id'], []).append(event)
            traces = [project(run, grouped.get(run['trace_id'], []), self.config) for run in runs]
            traces.sort(key=lambda r:r.get('last_activity') or '', reverse=True)
            data['traces'] = traces
            data['trace_overview'] = overview(traces, self.config, data['engines'])
            for engine in data['engines']:
                cells = [c for c in data['trace_overview']['matrix'] if c['engine_id']==engine['engine_id'] and c['status'] in ('FAILED','STALLED')]
                if cells:
                    engine['checks'].append({'name':'Service traces','status':'DEGRADED','reason':'; '.join(c['service_id']+': '+c['status']+' (latest observed run)' for c in cells)})
                    if engine['status'] not in ('OFFLINE','ERROR'): engine['status']='DEGRADED'
        except Exception:
            data['traces'] = []
            data['trace_overview'] = overview([], self.config, data['engines'])
            data['monitor_errors'].append('Trace normalization unavailable; independent monitoring continues')
        try:
            self.store.events(data['activity']+data['errors'])
            if time.monotonic()-self.last_snapshot >= self.config['snapshot_seconds']:
                self.store.save(data)
                self.last_snapshot=time.monotonic()
        except Exception:
            data['monitor_errors'].append('Local monitoring history is unavailable; live sources are still displayed')
        with self.lock: self.data=data
        return data

    def snapshot(self):
        with self.lock: return copy.deepcopy(self.data)

    def start(self):
        if self.thread: return
        def loop():
            while not self.stop.is_set():
                try: self.collect()
                except Exception:
                    with self.lock: self.data['monitor_errors']=['Collection failed; displaying last observation with its original timestamp']
                self.stop.wait(self.config['refresh_seconds'])
        self.thread=threading.Thread(target=loop,daemon=True,name='dsmonitor-collector')
        self.thread.start()

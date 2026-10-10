"""Run only independent diagnostic commands; never operational engine entrypoints."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import load_config, read_env
from scripts.domain_daily import job_environment

REPOS={'mmonolith':'mmonolith','decision_engine':'decision_engine','devspace_one':'devspace-one','dsorchestrator':'dsorchestrator','crm':'devspace-crm'}


def _cycle(settings):
    base=Path(settings['projects'])
    # Same explicit credentials/environment resolution as the scheduled domain jobs.
    shared=job_environment(base)
    def run(pair):
        engine,repo=pair
        environment = shared if engine!='dsorchestrator' else {**os.environ,**read_env(base/repo/'.env')}
        environment={**environment,'DEVSPACE_DIAGNOSTIC_SCOPE':'domain daily launcher environment' if engine!='dsorchestrator' else 'dsorchestrator own environment'}
        environment={**environment,'DEVSPACE_SERVICE_ORGANIZATIONS':json.dumps(settings.get('service_organization_ids',{})),
            'DS_USAGE_ENGINE':'dsmonitor', 'DS_USAGE_PROCESS':'capability-'+engine,
            'PYTHONPATH':os.pathsep.join((str(ROOT/'instrumentation'),str(ROOT/'.domain_deps'),environment.get('PYTHONPATH','')))}
        if engine=='mmonolith':
            client_env=read_env(base/'devspace-crm/.env.local')
            environment.update(CLIENT_SUPABASE_URL=client_env.get('NEXT_PUBLIC_SUPABASE_URL',''), CLIENT_SUPABASE_KEY=client_env.get('SUPABASE_SERVICE_ROLE_KEY',''))
        profile=ROOT/'scripts/crm_capability_profile.json' if engine=='crm' else base/repo/'monitoring/profile.json'
        output=settings.get('capability_files',{}).get(engine,str(ROOT/'data/capabilities'/f'{engine}.json'))
        command=[sys.executable,str(ROOT/'scripts/capability_probe.py'),'--profile',str(profile),'--output',output]
        for org in settings['organization_ids']:command += ['--organization',org]
        def failed(reason):
            try:
                spec=json.loads(profile.read_text())
                now=datetime.now(timezone.utc).isoformat()
                report={'engine_id':engine,'service_capabilities':{service:{
                    'checked_at':now,'organization_ids':settings['organization_ids'],
                    'connectivity_status':'UNKNOWN','configuration_status':'UNVERIFIED',
                    'write_status':'UNVERIFIED','reason':reason,
                    'next_action':'Check the dsmonitor probe runner and engine monitoring profile.',
                    'reads':{table:{'status':'UNKNOWN','reason':reason} for table in contract['inputs']}
                } for service,contract in spec['services'].items()}}
                path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
                temp=path.with_suffix('.tmp')
                with os.fdopen(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:json.dump(report,f)
                temp.replace(path)
            except Exception: pass  # Existing verification expires even if publication fails.
            return {'engine_id':engine,'result':reason}
        try:
            proc=subprocess.run(command,cwd=base/repo,env=environment,timeout=settings.get('probe_timeout_seconds', 35),capture_output=True,text=True)
            return {'engine_id':engine,'result':'published'} if proc.returncode==0 else failed('Diagnostic worker failed; current capability is unverified.')
        except Exception:
            return failed('Diagnostic worker unavailable or timed out; current capability is unverified.')
    with ThreadPoolExecutor(max_workers=5) as pool: return list(pool.map(run,REPOS.items()))


def cycle(settings):
    # Shared with the integrated scheduler and legacy cron; never overlap probes.
    path=ROOT/'data/engine-capabilities.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return [{'result':'Probe cycle already running'}]
        stamp=ROOT/'data/engine-capabilities.last-cycle'
        try:
            if time.time()-float(stamp.read_text()) < settings.get('probe_interval_seconds',300):
                return [{'result':'Shared probe interval not due'}]
        except (OSError,ValueError): pass
        stamp.write_text(str(time.time()))
        return _cycle(settings)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--interval',type=int,default=300)
    args=parser.parse_args()
    if args.interval<30 or args.interval>3600:parser.error('Interval must be 30–3600 seconds')
    settings=load_config()
    while True:
        print(json.dumps(cycle(settings)),flush=True)
        if not args.watch:break
        time.sleep(args.interval)



if __name__=='__main__':main()

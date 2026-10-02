"""Run fresh domain research and evaluation, then verify execution readiness."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import load_config
from scripts.domain_daily import job_environment, dotenv
from services.domain_diagnostic import assess
from services.security import Sanitizer


def now():
    return datetime.now(timezone.utc).isoformat()


def invoke(base, repo, request, environment, timeout):
    environment = {**environment, 'PYTHONPATH': os.pathsep.join((str(base / repo), str(ROOT / '.domain_deps')))}
    try:
        process = subprocess.run([sys.executable, str(ROOT / 'scripts/domain_diagnostic_worker.py')],
            cwd=base / repo, input=json.dumps(request), env=environment, capture_output=True, text=True, timeout=timeout)
        lines = process.stdout.splitlines()
        result = json.loads(lines[-1]) if lines else {'ok': False, 'error_type': 'NoWorkerResult'}
        if process.returncode and result.get('ok'):
            return {'ok': False, 'error_type': 'WorkerExitFailure'}
        return result
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error_type': 'Timeout; write outcome may be ambiguous—inspect CRM before rerunning'}
    except Exception as exc:
        return {'ok': False, 'error_type': type(exc).__name__}


def run_cycle(settings, organization, topic, timeout=300):
    base = Path(settings['projects'])
    environment = job_environment(base)
    secrets = settings.get('secrets', []) + [v for k, v in environment.items()
        if any(s in k.upper() for s in ('SECRET', 'TOKEN', 'PASSWORD', 'KEY')) and len(v) > 5]
    sanitizer = Sanitizer(secrets)
    directory = Path(settings['diagnostic_dir'])
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (organization + '.lock')).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A diagnostic cycle is already running for this organization') from None
        run_id = str(uuid4())
        context = dict(workflow_run_id=run_id, correlation_id=run_id, service_id='domain_merchant', organization_id=organization)
        report = {**context, 'started_at': now(), 'status': 'RUNNING', 'topic': topic['niche'], 'stages': {}}
        path = directory / (run_id + '.json')
        def save():
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(sanitizer.clean(report), indent=2))
            temporary.chmod(0o600)
            temporary.replace(path)
        save()
        args = ['--organization', organization, '--run-key', 'diagnostic-' + run_id, '--niche', topic['niche']]
        for keyword in topic['keywords']:
            args += ['--keyword', keyword]
        for location in topic.get('locations', []):
            args += ['--location', location]
        for key in ('sales_file', 'namebio_file', 'demand_file', 'buyers_file', 'availability_file', 'quote_file', 'assessment_file'):
            if topic.get(key):
                args += ['--' + key.replace('_', '-'), topic[key]]
        if topic.get('namebio_live', True):
            args += ['--namebio-live']
        for key in ('registrar_check', 'with_keywords'):
            if topic.get(key) is True:
                args += ['--' + key.replace('_', '-')]
        for stage, repo in [('research', 'mmonolith'), ('decision', 'decision_engine'), ('readiness', 'devspace-one')]:
            if stage == 'decision' and not report['stages']['research'].get('ok'):
                report['stages'][stage] = {'ok': False, 'error_type': 'Skipped: research did not complete; no unrelated evaluation launched'}
            else:
                print(f'{run_id}: {stage}', flush=True)
                report['stages'][stage] = invoke(base, repo, {'stage': stage, 'context': context, 'args': args}, environment, timeout)
            save()
        report['completed_at'] = now()
        report = assess(report)
        save()
        return sanitizer.clean(report), path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--organization', type=lambda v: str(UUID(v)))
    parser.add_argument('--topic', default='loans', help='Niche in scripts/domain_daily.json')
    parser.add_argument('--timeout', type=int, default=300, help='Per-stage timeout, seconds')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 900:
        parser.error('Timeout must be 1–900 seconds')
    settings = load_config()
    config = json.loads((ROOT / 'scripts/domain_daily.json').read_text())
    topic = next((t for t in config['topics'] if t['niche'] == args.topic), None)
    if not topic:
        parser.error('Topic must exist in scripts/domain_daily.json')
    organization = args.organization or config.get('organization_id') or dotenv(Path(settings['projects']) / 'devspace-one/.env').get('DOMAIN_MERCHANT_ORG_ID')
    if not organization:
        parser.error('--organization is required')
    organization = str(UUID(organization))
    if organization not in settings['organization_ids']:
        parser.error('Organization must be in DSMONITOR_ORGANIZATION_IDS')
    report, path = run_cycle(settings, organization, topic, args.timeout)
    print(json.dumps({'workflow_run_id': report['workflow_run_id'], 'status': report['status'], 'report': str(path), 'gaps': report['gaps']}, indent=2))
    return 1 if report['status'] == 'FAILED' else 2 if report['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())

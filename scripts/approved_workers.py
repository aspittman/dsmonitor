"""Process supported, already-approved zero-spend requests; never approve or send."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from domain_daily import job_environment

ROOT = Path(__file__).resolve().parents[1]


def jobs():
    scope = json.loads((ROOT / 'scripts/client_monitoring_scope.json').read_text())
    config = json.loads((ROOT / 'scripts/domain_daily.json').read_text())
    environment = job_environment()
    domain = config.get('organization_id') or environment.get('DOMAIN_MERCHANT_ORG_ID')
    if not domain:
        raise ValueError('Explicit domain organization required')
    yield 'domain-review', 'devspace-one', ['-m', 'core.domain_review_worker', '--organization', domain]
    yield 'domain-feedback', 'mmonolith', ['-m', 'services.domain_intelligence', '--organization', domain, '--learn']
    for organization in scope['devspace_clients']:
        yield 'client-brief', 'devspace-one', ['-m', 'services.devspace_clients.worker', '--organization', organization]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    selected = list(jobs())
    if args.dry_run:
        print(json.dumps({'jobs': [{'job': label, 'repository': repo, 'argv': argv}
            for label, repo, argv in selected], 'approval': 'Existing CRM approval required by each execution worker',
            'external_calls_authorized': False, 'send_authorized': False, 'purchase_authorized': False}, indent=2))
        return 0
    folder = ROOT / 'data/approved-workers'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'scheduler.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Approved-request worker already running')
            return 0
        environment = job_environment()
        failures = 0
        review_recorded = False
        for label, repo, argv in selected:
            if label == 'domain-feedback' and not review_recorded:
                print(json.dumps({'job': label, 'outcome': 'SKIPPED_NO_NEW_RESULT'}), flush=True)
                continue
            env = {**environment, 'PYTHONPATH': os.pathsep.join((
                str(ROOT.parent / repo), str(ROOT / 'instrumentation'), str(ROOT / '.domain_deps'), environment.get('PYTHONPATH', '')))}
            try:
                # Worker payloads are retained in their own outboxes, not cron output.
                result = subprocess.run([sys.executable, *argv], cwd=ROOT.parent / repo,
                    env={**env,'DS_USAGE_ENGINE':'mmonolith' if repo=='mmonolith' else 'devspace_one','DS_USAGE_PROCESS':label}, capture_output=True, text=True, timeout=180)
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired):
                code = 1
            failures += code != 0
            outcome = 'FAILED' if code else 'CHECK_COMPLETED'
            if code == 0:
                try:
                    payload = json.loads(result.stdout)
                    if payload.get('status') == 'IDLE':
                        outcome = 'IDLE'
                    elif payload.get('execution_result_id'):
                        UUID(payload['execution_result_id'])
                        outcome = 'RESULT_RECORDED'
                    elif 'feedback_ids' in payload:
                        outcome = 'FEEDBACK_RECORDED' if payload['feedback_ids'] else 'NO_NEW_FEEDBACK'
                except (ValueError, TypeError, AttributeError):
                    pass
            if label == 'domain-review':
                review_recorded = outcome == 'RESULT_RECORDED'
            print(json.dumps({'checked_at': datetime.now(timezone.utc).isoformat(),
                'job': label, 'organization_id': argv[argv.index('--organization') + 1],
                'exit_code': code, 'outcome': outcome}), flush=True)
        return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())

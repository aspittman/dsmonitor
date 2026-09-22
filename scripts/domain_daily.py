"""Daily DevSpace domain jobs. Invoked by cron with a single stage argument."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

ROOT = Path('/home/aaron/MyBotz')
CONFIG = Path(__file__).with_name('domain_daily.json')


def dotenv(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.removeprefix('export ').split('=', 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def run(repo, args, environment):
    environment = {**environment, 'PYTHONPATH': os.pathsep.join((
        str(ROOT / repo), str(ROOT / 'dsmonitor/.domain_deps'),
        environment.get('PYTHONPATH', '')))}
    subprocess.run([sys.executable, *args], cwd=ROOT / repo,
                   env=environment, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('research', 'decide', 'outreach'))
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    dev = dotenv(ROOT / 'devspace-one/.env')
    monolith = dotenv(ROOT / 'mmonolith/.env')
    decision = dotenv(ROOT / 'decision_engine/.env')
    org = str(UUID(config.get('organization_id') or dev['DOMAIN_MERCHANT_ORG_ID']))
    common = {**os.environ, **dev, **monolith, **decision}
    common['CRM_BASE_URL'] = common.get('CRM_BASE_URL') or common.get('CRM_API_URL', '')
    common['BOT_API_SECRET'] = common.get('BOT_API_SECRET') or common.get('CRM_BOT_API_SECRET', '')
    common['CRM_API_URL'] = common.get('CRM_API_URL') or common['CRM_BASE_URL']
    common['CRM_API_SECRET'] = common.get('CRM_API_SECRET') or common['BOT_API_SECRET']
    common['APOLLO_SENDING_EMAIL'] = config['apollo_sender_email']
    if args.stage == 'research':
        run('mmonolith', ['-m', 'services.domain_intelligence', '--organization', org, '--learn'], common)
        for topic in config['topics']:
            command = ['-m', 'services.domain_intelligence.discover',
                       '--organization', org, '--run-key',
                       f"{datetime.now().astimezone().date()}-{topic['niche']}",
                       '--niche', topic['niche'], '--sync-crm']
            for keyword in topic['keywords']:
                command += ['--keyword', keyword]
            for location in topic.get('locations', []):
                command += ['--location', location]
            if topic.get('namebio_live', True):
                command += ['--namebio-live']
            for key, flag in [('sales_file', '--sales-file'), ('namebio_file', '--namebio-file'),
                              ('demand_file', '--demand-file'), ('buyers_file', '--buyers-file'),
                              ('availability_file', '--availability-file')]:
                if topic.get(key):
                    command += [flag, topic[key]]
            if topic.get('registrar_check'):
                command += ['--registrar-check']
            run('mmonolith', command, common)
    elif args.stage == 'decide':
        run('decision_engine', ['main.py', '--organization', org,
                                '--trigger', 'SCHEDULED_REVIEW'], common)
    else:
        run('devspace-one', ['jobs/run_service.py', 'afternic_sync',
                             '--organization-id', org], common)
        run('devspace-one', ['jobs/run_service.py', 'apollo_outreach',
                             '--organization-id', org], common)
        run('devspace-one', ['-m', 'core.apollo_delivery', '--organization', org], common)


if __name__ == '__main__':
    main()

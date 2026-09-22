"""Evidence collection never launches a source engine or calls its CLI."""
import hashlib
import json
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from adapters.base import timestamp, epoch, get_json
from models import EngineStatus

PROJECTS = {'mmonolith': ('MMonolith', 'mmonolith'), 'decision_engine': ('Decision Engine', 'decision_engine'),
            'devspace_one': ('DevSpace One', 'devspace-one'), 'dsorchestrator': ('dsorchestrator', 'dsorchestrator')}


def process_alive(root):
    denied = False
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid(): continue
        try:
            args = (p/'cmdline').read_bytes().split(b'\0')
            if not args or not re.match(r'^(python[\d.]*|uvicorn|gunicorn)$', Path(args[0].decode()).name): continue
            # Exact cwd or absolute entrypoint; never match shell/grep/monitor command text.
            if (p/'cwd').resolve() == root or any(a.decode(errors='replace').startswith(str(root)+'/') and a.endswith(b'.py') for a in args[1:]): return True
        except (OSError, PermissionError): denied = True
    return None if denied else False


def collect_logs(root, engine, limit=50, extra_files=(), log_timezone=""):
    paths = sorted(set((root/'logs').glob('*.log')) | {Path(p) for p in extra_files})
    activity, errors = [], []
    for path in paths[:10]:
        with path.open('rb') as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size-65536))
            if size > 65536: f.readline()
            lines = f.read().decode(errors='replace').splitlines()[-100:]
        for line in lines:
            match = re.match(r'^(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:\d\d)?)', line)
            data = {}
            try: data = json.loads(line)
            except (ValueError, TypeError): pass
            if not isinstance(data, dict): data = {}
            raw_time = data.get('timestamp') or data.get('time') or (match[1].replace(',', '.') if match else None)
            at = timestamp(raw_time)
            if isinstance(raw_time, str):
                try:
                    parsed = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
                    if parsed.tzinfo is None:
                        at = parsed.replace(tzinfo=ZoneInfo(log_timezone)).astimezone(timezone.utc).isoformat() if log_timezone else None
                except ValueError:
                    at = None
            if data:
                bad = str(data.get('level', '')).upper() in ('ERROR','CRITICAL') or str(data.get('status', '')).upper() in ('ERROR','FAILED') or bool(data.get('error_message'))
            else:
                bad = bool(re.search(r'\b(ERROR|CRITICAL|FAILED)\b', line, re.I) or re.match(r'^(?:[\w.]+(?:Error|Exception)|Exception):', line))
            if not raw_time and (not bad or line[:1].isspace()): continue
            # Undated exception summaries are evidence, but their occurrence time is unknown.
            # Avoid importing customer payloads from arbitrary stdout.
            message = str(data.get('error_message') or data.get('event') or data.get('message') or line)
            row = {'id': f'{engine}:{path.name}:' + hashlib.sha256(line.encode()).hexdigest()[:24], 'engine': engine, 'timestamp': at,
                   'status': 'ERROR' if bad else 'OBSERVED', 'message': message[:2000] if bad else f'Activity recorded in {path.name}',
                   'process_id': data.get('workflow_run_id'), 'organization_id': data.get('organization_id'),
                   'process_type': data.get('workflow_type'), 'stage': data.get('stage'), 'retries': None, 'source': path.name,
                   'observed_at': datetime.now(timezone.utc).isoformat(), 'source_timestamp':raw_time, 'time_basis':'source timestamp' if at else 'Occurrence time or timezone unavailable; observed in log tail'}
            activity.append(row)
            if bad: errors.append(row)
    def grouped(rows):
        unique = {}
        for row in rows:
            if row['id'] not in unique:
                unique[row['id']] = dict(row, occurrences_in_tail=0)
            unique[row['id']]['occurrences_in_tail'] += 1
        return sorted(unique.values(), key=lambda x:x['timestamp'] or '', reverse=True)[:limit]
    return grouped(activity), grouped(errors)


def collect(engine, config):
    name, directory = PROJECTS[engine]
    result = EngineStatus(engine, name)
    root = (Path(config['projects'])/directory).resolve()
    alive = process_alive(root)
    result.checks.append({'name': 'Local process', 'status': 'ONLINE' if alive else 'UNKNOWN',
                          'reason': 'Matching Python process observed' if alive else 'No matching persistent process observed; these engines can run as batch jobs'})
    result.status = 'ONLINE' if alive else 'UNKNOWN'
    try:
        result.activity, result.errors = collect_logs(root, engine, extra_files=config.get('log_files',{}).get(engine,[]), log_timezone=config.get('log_timezone',''))
        if result.activity: result.last_activity = next((r['timestamp'] for r in result.activity if r['timestamp']), None)
        if result.errors: result.last_error = result.errors[0]['message']
        result.checks.append({'name':'Logs', 'status':'HEALTHY' if result.activity else 'UNKNOWN', 'reason': 'Bounded log tail; timestamps without a known timezone show time unknown; not a complete daily count' if result.activity else 'No readable log events available'})
    except Exception:
        result.checks.append({'name':'Logs','status':'UNKNOWN','reason':'Could not read or parse log source'})
    url = config['health_urls'].get(engine)
    if url:
        try:
            data = get_json(url, config['timeout_seconds'])
            good = isinstance(data, dict) and str(data.get('status', '')).upper() in ('HEALTHY','OK')
            result.status = 'HEALTHY' if good else 'DEGRADED'
            result.checks.append({'name':'API', 'status':result.status,'reason':'Health endpoint reports healthy' if good else 'API responded but did not report healthy'})
        except Exception:
            result.status = 'DEGRADED' if alive else 'OFFLINE'
            result.checks.append({'name':'API','status':'OFFLINE','reason':'Configured endpoint unavailable or invalid'})
    heartbeat = config['heartbeat_files'].get(engine)
    if heartbeat:
        try:
            data = json.loads(Path(heartbeat).read_text())
            result.last_heartbeat = timestamp(data['timestamp'])
            age = datetime.now(timezone.utc).timestamp() - epoch(result.last_heartbeat)
            status = 'ONLINE' if 0 <= age <= config['heartbeat_max_age'] else 'STALE'
            result.checks.append({'name':'Heartbeat','status':status,'reason':f'Configured heartbeat freshness limit: {config["heartbeat_max_age"]}s'})
            if status == 'STALE': result.status = 'STALE'
            elif result.status == 'UNKNOWN': result.status = 'ONLINE'
        except Exception:
            result.checks.append({'name':'Heartbeat','status':'UNKNOWN','reason':'Heartbeat missing or invalid'})
    return result.dict()

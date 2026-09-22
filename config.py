"""Local configuration. Source projects are never imported or executed."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_env(path):
    result = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and not key.startswith('#'):
                result[key.removeprefix('export ').strip()] = value.strip().strip('\"\'')
    return result


def load_config():
    e = read_env(ROOT / '.env') | dict(os.environ)
    base = Path(e.get('DSMONITOR_PROJECTS', ROOT.parent))
    one = read_env(base / 'devspace-one/.env')
    crm = read_env(base / 'devspace-crm/.env.local')
    # Existing credentials stay server-side; explicit monitor settings override discovery.
    defaults = {
        'projects': str(base), 'refresh_seconds': 10, 'snapshot_seconds': 120,
        'timeout_seconds': 3, 'crm_context_seconds': 120, 'retention_days': 30, 'limit': 200,
        'database': str(ROOT / 'data/dsmonitor.db'), 'port': 5055,
        'orchestrator_sqlite': str(base / 'dsorchestrator/data/orchestrator.sqlite3'),
        'orchestrator_dsn': '', 'supabase_dsn': '',
        'crm_url': one.get('CRM_BASE_URL', ''),
        'crm_token': one.get('CRM_BOT_API_SECRET', crm.get('BOT_API_SECRET', '')),
        'supabase_url': crm.get('NEXT_PUBLIC_SUPABASE_URL', ''),
        'supabase_key': crm.get('NEXT_PUBLIC_SUPABASE_ANON_KEY', ''),
        'organization_ids': [], 'stale_seconds': {}, 'health_urls': {}, 'heartbeat_files': {},
        'decision_trace_log': str(ROOT / 'logs/domain_decide.log'), 'trace_registry': {}, 'trace_thresholds': {}, 'trace_files': {}, 'trace_limit': 1000,
        'heartbeat_max_age': 120, 'extra_processes': [], 'log_files': {}, 'log_timezone': '',
    }
    for key, default in list(defaults.items()):
        value = e.get('DSMONITOR_' + key.upper())
        if value is not None:
            defaults[key] = json.loads(value) if isinstance(default, (list, dict)) else type(default)(value)
    from uuid import UUID
    defaults['organization_ids'] = [str(UUID(x)) for x in defaults['organization_ids']]
    for key in ('refresh_seconds', 'snapshot_seconds', 'timeout_seconds', 'retention_days', 'limit', 'heartbeat_max_age', 'crm_context_seconds'):
        if defaults[key] <= 0:
            raise ValueError(key + ' must be positive')
    if len(defaults['organization_ids']) > 20:
        raise ValueError('At most 20 organizations per monitor instance')
    if not Path(defaults['database']).resolve().is_relative_to((ROOT / 'data').resolve()):
        raise ValueError('Monitoring database must be inside dsmonitor/data')
    defaults['secrets'] = [v for source in (e, one, crm) for k, v in source.items()
                           if any(s in k.upper() for s in ('SECRET', 'TOKEN', 'PASSWORD', 'KEY', 'DSN')) and len(v) > 5]
    return defaults

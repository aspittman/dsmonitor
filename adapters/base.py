import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from services.security import validate_url


def timestamp(value):
    if value is None or value == '': return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError): return None


def epoch(value):
    parsed = timestamp(value)
    return datetime.fromisoformat(parsed).timestamp() if parsed else None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args): return None


class HTTPReadError(ConnectionError):
    """Safe transport metadata; never retains raw response bodies or credentials."""
    def __init__(self, status, database_code=None):
        super().__init__('HTTP ' + str(status))
        self.http_status = status
        self.database_code = database_code


def get_json(url, timeout=3, headers=None, query=''):
    url = validate_url(url)
    request = Request(url + query, headers={'Accept': 'application/json', **(headers or {})}, method='GET')
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(4_000_001)
            if len(data) > 4_000_000: raise ValueError('Response exceeds monitoring limit')
            return json.loads(data)
    except HTTPError as exc:
        code = None
        try:
            payload = json.loads(exc.read(8192))
            candidate = payload.get('code') if isinstance(payload, dict) else None
            if isinstance(candidate, str) and re.fullmatch(r'(?:[0-9A-Z]{5}|PGRST\d{3})', candidate):
                code = candidate
        except (ValueError, OSError):
            pass
        finally:
            exc.close()
        raise HTTPReadError(exc.code, code) from None
    except (URLError, TimeoutError, OSError):
        raise ConnectionError('Endpoint unreachable or timed out') from None


@contextmanager
def readonly_sqlite(path):
    p = Path(path)
    if not p.is_file(): raise FileNotFoundError('Source database is not configured or missing')
    db = sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    try: yield db
    finally: db.close()


@contextmanager
def readonly_postgres(dsn, timeout=3):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, connect_timeout=max(1, int(timeout)), options='-c default_transaction_read_only=on -c statement_timeout=3000', row_factory=dict_row) as db:
        db.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        yield db

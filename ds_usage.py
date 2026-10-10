"""Local HTTP body accounting and shared cloud backoff. Never stores URLs or payloads."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
ACTOR = ContextVar('usage_actor', default=None)


class CloudBackoff(OSError):
    pass


def database():
    return Path(os.environ.get('DS_USAGE_DATABASE', ROOT / 'data/consumption.sqlite3'))


@contextmanager
def connect():
    path = database()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    try:
        path.chmod(0o600)
        db.executescript('''
        CREATE TABLE IF NOT EXISTS usage_hourly (
          hour INTEGER, engine TEXT, process TEXT, provider TEXT, endpoint TEXT,
          requests INTEGER DEFAULT 0, sent INTEGER DEFAULT 0, received INTEGER DEFAULT 0,
          errors INTEGER DEFAULT 0, suppressed INTEGER DEFAULT 0, duration_ms INTEGER DEFAULT 0,
          PRIMARY KEY(hour,engine,process,provider,endpoint));
        CREATE TABLE IF NOT EXISTS cloud_backoff(provider TEXT PRIMARY KEY, until REAL, status INTEGER);
        CREATE TABLE IF NOT EXISTS usage_meta(key TEXT PRIMARY KEY, value TEXT);
        ''')
        if 'largest_response' not in {r[1] for r in db.execute('PRAGMA table_info(usage_hourly)')}:
            try:
                db.execute('ALTER TABLE usage_hourly ADD COLUMN largest_response INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                if 'largest_response' not in {r[1] for r in db.execute('PRAGMA table_info(usage_hourly)')}:
                    raise
        db.execute("INSERT OR IGNORE INTO usage_meta VALUES('started_at',?)", (datetime.now(timezone.utc).isoformat(),))
        yield db
        db.commit()
    finally:
        db.close()


def identity():
    return ACTOR.get() or (os.environ.get('DS_USAGE_ENGINE', 'unattributed'), os.environ.get('DS_USAGE_PROCESS', 'unattributed'))


@contextmanager
def actor(engine, process):
    token = ACTOR.set((engine, process))
    try:
        yield
    finally:
        ACTOR.reset(token)


def destination(url):
    parsed = urlparse(url)
    host = parsed.hostname or ''
    crm = urlparse(os.environ.get('CRM_BASE_URL') or os.environ.get('CRM_API_URL') or '').hostname
    if host.endswith(('.supabase.co', '.supabase.com')):
        provider = 'supabase'
    elif host.endswith('.vercel.app') or host == crm:
        provider = 'vercel'
    elif host in ('localhost', '127.0.0.1', '::1'):
        provider = 'local'
    else:
        provider = 'external'
    # Keep fixed API resource names only; query strings, IDs and arbitrary paths never persist.
    known = ('monitoring-capabilities', 'monitoring-context', 'context', 'work-context', 'pending-work',
             'review-feedback', 'organizations', 'intelligence', 'results', 'evaluations', 'observe-review',
             'claim-review', 'claim-client-brief', 'market_signals', 'intelligence_reports', 'execution_results',
             'organization_services', 'health', 'token')
    tail = parsed.path.rstrip('/').split('/')[-1]
    return provider, tail if tail in known else 'other'


def record(url, sent=0, received=0, status=200, elapsed=0, suppressed=False):
    provider, endpoint = destination(url)
    engine, process = identity()
    try:
        with connect() as db:
            db.execute('''INSERT INTO usage_hourly(hour,engine,process,provider,endpoint,requests,sent,received,errors,suppressed,duration_ms,largest_response) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(hour,engine,process,provider,endpoint) DO UPDATE SET
              requests=requests+excluded.requests,sent=sent+excluded.sent,received=received+excluded.received,
              errors=errors+excluded.errors,suppressed=suppressed+excluded.suppressed,
              duration_ms=duration_ms+excluded.duration_ms,largest_response=max(largest_response,excluded.largest_response)''',
              (int(time.time() // 3600) * 3600, engine[:80], process[:100], provider, endpoint,
               int(not suppressed), max(0, int(sent)), max(0, int(received)),
               int(not suppressed and (status == 0 or status >= 400)), int(suppressed), int(elapsed * 1000), max(0, int(received))))
            if provider in ('vercel', 'supabase') and status in (402, 429, 503):
                delay = 900 if status in (402, 429) else 120
                db.execute('''INSERT INTO cloud_backoff VALUES(?,?,?) ON CONFLICT(provider)
                    DO UPDATE SET until=max(until,excluded.until),status=excluded.status''',
                    (provider, time.time() + delay, status))
            db.execute('DELETE FROM usage_hourly WHERE hour < ?', (time.time() - 90 * 86400,))
    except (OSError, sqlite3.Error, ValueError, TypeError):
        pass  # Accounting failure never changes the business operation.


def guard(url):
    provider, _ = destination(url)
    if provider not in ('vercel', 'supabase'):
        return
    try:
        with connect() as db:
            row = db.execute('SELECT until FROM cloud_backoff WHERE provider=?', (provider,)).fetchone()
    except (OSError, sqlite3.Error):
        return
    if row and row[0] > time.time():
        record(url, suppressed=True, status=0)
        raise CloudBackoff('Cloud request deferred after quota/rate-limit or service failure')


def summary(days=7):
    with connect() as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('''SELECT engine,process,provider,endpoint,
          sum(requests) requests,sum(sent) sent_bytes,sum(received) received_bytes,
          sum(errors) errors,sum(suppressed) suppressed,sum(duration_ms) duration_ms,max(largest_response) largest_response_bytes
          FROM usage_hourly WHERE hour>=? GROUP BY engine,process,provider,endpoint
          ORDER BY sum(received)+sum(sent) DESC''', (time.time() - days * 86400,))]
        started = db.execute("SELECT value FROM usage_meta WHERE key='started_at'").fetchone()[0]
        backoff = [dict(r) for r in db.execute('SELECT provider,until,status FROM cloud_backoff WHERE until>?', (time.time(),))]
        daily = [dict(r) for r in db.execute('''SELECT date(hour,'unixepoch') day,sum(sent) sent_bytes,
          sum(received) received_bytes,sum(requests) requests FROM usage_hourly WHERE hour>=?
          GROUP BY day ORDER BY day''', (time.time() - days * 86400,))]
        today = [dict(r) for r in db.execute('''SELECT engine,process,sum(sent)+sum(received) bytes,
          sum(requests) requests,max(largest_response) largest_response_bytes FROM usage_hourly
          WHERE hour>=? AND hour<? AND provider!='local' GROUP BY engine,process''',
          (int(time.time()//86400)*86400, (int(time.time()//86400)+1)*86400))]
    from usage_limits import evaluate
    alerts, thresholds = evaluate(today)
    provider_usage = {}
    try:
        provider_usage = json.loads((ROOT / 'data/provider-usage.json').read_text())
    except (OSError, ValueError):
        pass
    return {'started_at': started, 'window_days': days, 'rows': rows, 'daily': daily, 'backoff': backoff,
            'provider_usage': provider_usage, 'alerts': alerts, 'thresholds': thresholds,
            'totals': {key: sum(r[key] for r in rows) for key in ('requests', 'sent_bytes', 'received_bytes', 'errors', 'suppressed')},
            'coverage': 'Instrumented local Python HTTP calls only, starting at the time shown. Decoded body bytes exclude compression effects, TLS/headers and are not provider billing totals. Streaming and some error response bodies, CRM-to-Supabase traffic, database wire traffic, browsers, and remote workers are not included. Log ingestion is a separate provider metric.'}


class CountedResponse:
    def __init__(self, response, url, sent, started):
        self.response, self.url, self.sent, self.started = response, url, sent, started
        self.received, self.done = 0, False
    def __getattr__(self, name):
        return getattr(self.response, name)
    def read(self, *args, **kwargs):
        data = self.response.read(*args, **kwargs)
        self.received += len(data)
        return data
    def close(self):
        if not self.done:
            self.done = True
            record(self.url, self.sent, self.received, getattr(self.response, 'status', 200), time.monotonic() - self.started)
        self.response.close()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


def install():
    """Instrument standard urllib and requests used by the configured Python launchers."""
    import urllib.request
    from urllib.error import HTTPError
    if getattr(urllib.request.OpenerDirector.open, '_ds_usage', False):
        return
    original = urllib.request.OpenerDirector.open
    def opened(opener, request, *args, **kwargs):
        url = request.full_url if hasattr(request, 'full_url') else request
        guard(url)
        sent = len(getattr(request, 'data', None) or kwargs.get('data') or b'')
        began = time.monotonic()
        try:
            return CountedResponse(original(opener, request, *args, **kwargs), url, sent, began)
        except HTTPError as error:
            # Error responses are counted without reading or retaining their payload.
            record(url, sent, 0, error.code, time.monotonic() - began)
            raise
        except OSError:
            record(url, sent, 0, 0, time.monotonic() - began)
            raise
    opened._ds_usage = True
    urllib.request.OpenerDirector.open = opened
    try:
        import requests
    except ImportError:
        return
    original_send = requests.Session.send
    sending = ContextVar("usage_sending", default=False)
    def send(session, request, **kwargs):
        if sending.get():
            return original_send(session, request, **kwargs)
        token = sending.set(True)
        try:
            guard(request.url)
        except CloudBackoff as exc:
            sending.reset(token)
            raise requests.RequestException(str(exc)) from None
        began = time.monotonic()
        body = request.body or b''
        sent = len(body.encode() if isinstance(body, str) else body) if isinstance(body, (str, bytes)) else 0
        try:
            response = original_send(session, request, **kwargs)
            # Do not force a streaming response into memory just to measure it.
            received = 0 if kwargs.get('stream') else len(response.content)
            for hop in response.history:
                hop_body = hop.request.body or b''
                hop_sent = len(hop_body.encode() if isinstance(hop_body, str) else hop_body) if isinstance(hop_body, (str, bytes)) else 0
                record(hop.request.url, hop_sent, len(hop.content), hop.status_code)
            record(response.url or request.url, sent if not response.history else 0, received, response.status_code, time.monotonic() - began)
            return response
        except requests.RequestException:
            record(request.url, sent, 0, 0, time.monotonic() - began)
            raise
        finally:
            sending.reset(token)
    requests.Session.send = send

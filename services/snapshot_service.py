from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
from pathlib import Path


class SnapshotStore:
    def __init__(self, path, retention_days=30):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention = retention_days*86400
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS snapshot_time ON snapshots(timestamp);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, timestamp REAL NOT NULL, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS event_time ON events(timestamp);
            CREATE TABLE IF NOT EXISTS workflow_runs(trace_id TEXT PRIMARY KEY, observed_at REAL NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trace_events(trace_event_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, timestamp TEXT, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS trace_run ON trace_events(trace_id, timestamp);
            CREATE INDEX IF NOT EXISTS trace_observed ON workflow_runs(observed_at);''')
            db.executescript('''CREATE TABLE IF NOT EXISTS service_health_history(
                id INTEGER PRIMARY KEY, service_id TEXT NOT NULL, engine_id TEXT NOT NULL,
                timestamp REAL NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS service_health_time ON service_health_history(service_id, engine_id, timestamp);''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db: yield db
        finally: db.close()

    def save(self, data):
        # Only normalized monitoring fields enter history, never raw CRM payloads.
        stored = {k:data[k] for k in ('collected_at','engines','processes','summary','coverage')}
        stored['service_health'] = data.get('trace_overview', {}).get('matrix', [])
        with self.connect() as db:
            now=time.time()
            db.execute('INSERT INTO snapshots(timestamp,data) VALUES(?,?)',(now,json.dumps(stored)))
            db.execute('DELETE FROM snapshots WHERE timestamp < ?', (now-self.retention,))
            db.execute('DELETE FROM events WHERE timestamp < ?', (now-self.retention,))

    def events(self, rows):
        from adapters.base import epoch
        with self.connect() as db:
            for row in rows:
                at=epoch(row.get('timestamp')) or epoch(row.get('observed_at'))
                if not at or at < time.time()-self.retention: continue
                identity = {k:row.get(k) for k in ('id','engine','timestamp','status','message','process_id','stage','source','reference_id')}
                key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO events(id,timestamp,data) VALUES(?,?,?)',(key,at,json.dumps(row)))

    def history(self, kind='snapshots', limit=100):
        if kind not in ('snapshots','events'): raise ValueError('Unknown history kind')
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(f'SELECT data FROM {kind} ORDER BY timestamp DESC LIMIT ?', (min(limit,500),))]

    def save_traces(self, runs, events):
        """Idempotent normalized observations in the existing monitoring database."""
        with self.connect() as db:
            for run in runs:
                db.execute('INSERT INTO workflow_runs(trace_id,observed_at,data) VALUES(?,?,?) ON CONFLICT(trace_id) DO UPDATE SET observed_at=excluded.observed_at,data=excluded.data',
                           (run['trace_id'],time.time(),json.dumps(run)))
            for event in events:
                db.execute('INSERT OR IGNORE INTO trace_events(trace_event_id,trace_id,timestamp,data) VALUES(?,?,?,?)',
                           (event['trace_event_id'],event['trace_id'],event.get('timestamp'),json.dumps(event)))
            db.execute('DELETE FROM workflow_runs WHERE observed_at < ?', (time.time()-self.retention,))
            db.execute('DELETE FROM trace_events WHERE trace_id NOT IN (SELECT trace_id FROM workflow_runs)')

    def traces(self, limit=1000):
        with self.connect() as db:
            rows = db.execute('SELECT trace_id,data FROM workflow_runs ORDER BY observed_at DESC LIMIT ?', (limit,)).fetchall()
            runs = [json.loads(r[1]) for r in rows]
            events = []
            for rid,_ in rows:
                events.extend(json.loads(r[0]) for r in db.execute('SELECT data FROM trace_events WHERE trace_id=? ORDER BY timestamp', (rid,)))
            return runs, events

    def service_health(self, cells):
        """Record observed transitions, not inferred business recovery timestamps."""
        from adapters.base import timestamp
        with self.connect() as db:
            now = time.time()
            for cell in cells:
                params = (cell['service_id'], cell['engine_id'])
                prior = db.execute('SELECT status FROM service_health_history WHERE service_id=? AND engine_id=? ORDER BY id DESC LIMIT 1', params).fetchone()
                if not prior or prior[0] != cell['status']:
                    db.execute('INSERT INTO service_health_history(service_id,engine_id,timestamp,status,reason) VALUES(?,?,?,?,?)', (*params, now, cell['status'], cell['reason']))
                rows = db.execute('SELECT timestamp,status,reason FROM service_health_history WHERE service_id=? AND engine_id=? ORDER BY id DESC LIMIT 20', params).fetchall()
                cell['health_history'] = [{'observed_at': timestamp(at), 'status': status, 'reason': reason} for at, status, reason in rows]
                cell['recovered_at'] = None
                cell['previous_issue'] = None
                if cell['status'] in ('HEALTHY', 'IDLE'):
                    # UNKNOWN is lost coverage, never evidence of recovery.
                    bad = next((r for r in rows[1:] if r[1] in ('FAILED', 'DEGRADED', 'DISCONNECTED')), None)
                    if bad:
                        good = [r for r in rows if r[0] > bad[0] and r[1] in ('HEALTHY', 'IDLE')]
                        cell['recovered_at'] = timestamp(good[-1][0]) if good else None
                        cell['previous_issue'] = bad[2]
            db.execute('DELETE FROM service_health_history WHERE timestamp < ?', (now-self.retention,))

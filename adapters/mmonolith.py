from pathlib import Path
from datetime import datetime, timezone
from adapters.local import collect as collect_local
from adapters.base import readonly_sqlite, timestamp


def collect(config):
    result = collect_local('mmonolith', config)
    try:
        with readonly_sqlite(Path(config['projects'])/'mmonolith/data/demand_seeker.sqlite3') as db:
            today = datetime.now(timezone.utc).date().isoformat()
            for table, date, label in [('observations','collected_at','Observations today'),('report_history','generated_at','Reports today')]:
                n = db.execute(f'SELECT count(*) FROM {table} WHERE date({date})=date(?)', (today,)).fetchone()[0]
                result['metrics'][label] = n
            rows = db.execute('SELECT id,generated_at FROM report_history ORDER BY generated_at DESC LIMIT 20').fetchall()
            for r in rows:
                at = timestamp(r['generated_at'])
                if at: result['activity'].append({'id':f'mmonolith:report:{r["id"]}','engine':'mmonolith','timestamp':at,'status':'COMPLETED','message':'Research report stored','process_id':None,'organization_id':None,'process_type':None,'source':'report_history','reference_id':str(r['id'])})
            if rows: result['last_success'] = timestamp(rows[0]['generated_at'])
        result['checks'].append({'name':'Research store','status':'HEALTHY','reason':'Existing SQLite research tables readable; counts are UTC calendar-day totals'})
    except Exception:
        result['checks'].append({'name':'Research store','status':'UNKNOWN','reason':'Local research database missing or unreadable'})
    result['activity'].sort(key=lambda x:x['timestamp'] or '',reverse=True)
    if result['activity']: result['last_activity'] = result['activity'][0]['timestamp']
    return result

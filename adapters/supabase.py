from adapters.base import get_json, readonly_postgres
from models import EngineStatus


def collect(config):
    result = EngineStatus('supabase', 'Supabase / Database', infrastructure=True).dict()
    if not config['supabase_dsn'] and not (config['supabase_url'] and config['supabase_key']):
        result['checks'] = [{'name':'Database','status':'UNKNOWN','reason':'Independent database probe not configured'}]
        return result
    try:
        if config['supabase_dsn']:
            with readonly_postgres(config['supabase_dsn'], config['timeout_seconds']) as db:
                db.execute('SELECT 1').fetchone()
                if config.get('supabase_overview'):
                    row=db.execute('SELECT public.dsmonitor_overview() AS overview').fetchone()
                    result['database_overview']=row['overview']
            reason = 'Independent PostgreSQL SELECT 1 succeeded in a read-only session; schema/permissions not verified'
            if config.get('supabase_overview'):
                reason = 'Direct read-only PostgreSQL connection and aggregate operational summary succeeded'
        else:
            rows = get_json(config['supabase_url'].rstrip('/')+'/rest/v1/organizations', config['timeout_seconds'],
                            {'apikey':config['supabase_key'], 'Authorization':'Bearer '+config['supabase_key']}, '?select=id&limit=1')
            if not isinstance(rows, list): raise ValueError('Unexpected database response')
            reason = 'Independent PostgREST SELECT succeeded; RLS may hide rows. This proves connectivity, not service-role permissions'
        result['status'] = 'HEALTHY'
        result['checks'] = [{'name':'Database','status':'HEALTHY','reason':reason}]
    except ConnectionError as exc:
        result['status'] = 'ERROR' if str(exc).startswith('HTTP ') else 'OFFLINE'
        result['checks'] = [{'name':'Database','status':result['status'],'reason':str(exc)}]
        if getattr(exc, 'database_code', None) == '42501':
            # A PostgreSQL permission error proves the database answered. It
            # does not prove the monitoring role, or an engine role, can SELECT.
            result['status'] = 'ONLINE'
            result['dependency_status'] = 'UNKNOWN'
            result['monitoring_issue'] = 'The monitoring role cannot read organizations (42501). Database responded; engine permissions remain unverified.'
            result['checks'] = [
                {'name':'Database connectivity','status':'ONLINE','reason':'PostgreSQL answered the read request with permission-denied code 42501'},
                {'name':'Monitoring read access','status':'ERROR','reason':result['monitoring_issue']},
            ]
        elif str(exc) in ('HTTP 401','HTTP 403'):
            result['status'] = 'UNKNOWN'
            result['dependency_status']='UNKNOWN'
            result['monitoring_issue'] = str(exc) + ' — monitoring credential/access failed; database and engine health are not established'
            result['checks'][0]['reason'] = result['monitoring_issue']
    except Exception:
        result['status'] = 'ERROR'
        result['checks'] = [{'name':'Database','status':'ERROR','reason':'Database probe failed (connection, permissions, schema or configuration)'}]
    return result

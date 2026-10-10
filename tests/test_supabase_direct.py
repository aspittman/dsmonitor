from contextlib import contextmanager
from adapters import supabase


def test_direct_summary_uses_read_only_connection_and_never_http(monkeypatch):
    calls=[]
    class DB:
        def execute(self,query):
            calls.append(query)
            return self
        def fetchone(self):
            return {'overview':{'database_bytes':123,'connections':2}}
    @contextmanager
    def connect(dsn,timeout):
        assert dsn=='restricted-login'
        yield DB()
    monkeypatch.setattr(supabase,'readonly_postgres',connect)
    monkeypatch.setattr(supabase,'get_json',lambda *a,**k: (_ for _ in ()).throw(AssertionError('HTTP not needed')))
    result=supabase.collect({'supabase_dsn':'restricted-login','supabase_overview':1,'timeout_seconds':3})
    assert result['status']=='HEALTHY'
    assert result['database_overview']=={'database_bytes':123,'connections':2}
    assert calls==['SELECT 1','SELECT public.dsmonitor_overview() AS overview']
    assert 'restricted-login' not in str(result)

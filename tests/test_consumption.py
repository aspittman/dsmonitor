import json
from io import BytesIO
import pytest
import ds_usage

@pytest.fixture(autouse=True)
def isolated_usage(tmp_path, monkeypatch):
    monkeypatch.setenv('DS_USAGE_DATABASE', str(tmp_path/'usage.sqlite3'))

def test_accounting_attributes_bytes_without_storing_secrets():
    with ds_usage.actor('engine-a','review'):
        ds_usage.record('https://private.supabase.co/rest/v1/intelligence_reports?secret=private',sent=12,received=100)
    with ds_usage.actor('engine-b','probe'):
        ds_usage.record('https://private.vercel.app/api/monitoring-context',received=3,status=503)
    result=ds_usage.summary()
    assert result['totals']['received_bytes']==103
    assert result['rows'][0]['engine']=='engine-a'
    assert 'private' not in json.dumps(result['rows'])
    assert result['totals']['errors']==1

def test_quota_backoff_prevents_actual_requests():
    url='https://quota.supabase.co/rest/v1/intelligence_reports'
    ds_usage.record(url,status=402)
    with pytest.raises(ds_usage.CloudBackoff):
        ds_usage.guard(url)
    ds_usage.guard('http://localhost/health')
    result=ds_usage.summary()
    assert result['totals']['requests']==1
    assert result['totals']['suppressed']==1
    assert result['backoff'][0]['status']==402

def test_response_counts_consumed_bytes_once():
    response=ds_usage.CountedResponse(BytesIO(b'abcdef'),'https://example.org/data',2,ds_usage.time.monotonic())
    with response:
        assert response.read(2)==b'ab'
        assert response.read()==b'cdef'
    response.close()
    assert ds_usage.summary()['totals']['received_bytes']==6
    assert ds_usage.summary()['totals']['requests']==1

def test_usage_endpoint_is_local_and_rejects_invalid_windows(tmp_path):
    from app import create_app
    from config import load_config
    config=load_config()
    config['database']=str(tmp_path/'monitor.sqlite3')
    client=create_app(config,start_collector=False).test_client()
    assert client.get('/api/consumption?days=garbage').status_code==400
    assert client.get('/api/consumption?days=365').status_code==400
    assert client.get('/api/consumption?days=1').json['window_days']==1
    assert client.get('/api/consumption',base_url='http://evil.example').status_code==403

def test_warning_thresholds_use_current_utc_day_and_exclude_local(monkeypatch):
    with ds_usage.actor('engine-a','research'):
        ds_usage.record('https://research.example/data',received=2*1024*1024)
        ds_usage.record('http://localhost/data',received=100*1024*1024)
    result=ds_usage.summary()
    assert len(result['alerts'])==1
    alert=result['alerts'][0]
    assert alert['engine']=='engine-a' and alert['process']=='research'
    assert alert['bytes']==2*1024*1024
    assert alert['largest_response_bytes']==2*1024*1024
    assert alert['reasons']==['A large response was downloaded today']
    assert result['rows'][0]['largest_response_bytes']==100*1024*1024
    monkeypatch.setattr(ds_usage.time,'time',lambda: 0)
    assert ds_usage.summary()['alerts']==[]

def test_accounting_migrates_existing_database(monkeypatch):
    import sqlite3
    path=ds_usage.database()
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE usage_hourly(hour INTEGER,engine TEXT,process TEXT,provider TEXT,
          endpoint TEXT,requests INTEGER DEFAULT 0,sent INTEGER DEFAULT 0,received INTEGER DEFAULT 0,
          errors INTEGER DEFAULT 0,suppressed INTEGER DEFAULT 0,duration_ms INTEGER DEFAULT 0,
          PRIMARY KEY(hour,engine,process,provider,endpoint))''')
    ds_usage.record('https://example.org/data',received=7)
    assert ds_usage.summary()['rows'][0]['largest_response_bytes']==7

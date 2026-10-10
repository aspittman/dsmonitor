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

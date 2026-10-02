from urllib.parse import parse_qs
from scripts.client_direct_probe import probe_direct
from adapters.base import HTTPReadError
from services.freshness import project
from adapters.base import timestamp

ORG='11111111-1111-4111-8111-111111111111'
CONTRACT={'inputs':['intelligence_reports','execution_results']}
ENV={'CLIENT_SUPABASE_URL':'https://example.supabase.co','CLIENT_SUPABASE_KEY':'private-key'}


def test_direct_probe_is_bounded_authenticated_and_never_verifies_writes():
    calls=[]
    def get(url, timeout, headers, query):
        calls.append((url,headers,parse_qs(query.lstrip('?'))))
        return [{'id':'row','organization_id':ORG,'is_enabled':True}]
    report=probe_direct(CONTRACT,[ORG],ENV,get)
    assert report['connectivity_status']=='CONNECTED'
    assert report['configuration_status']=='VERIFIED'
    assert report['write_status']=='UNVERIFIED'
    assert len(calls)==3
    for url,headers,params in calls:
        assert url.startswith('https://example.supabase.co/rest/v1/')
        assert params['limit']==['1']
        assert params['organization_id']==['eq.'+ORG]
        assert headers['apikey']=='private-key'
    assert calls[1][2]['service_id']==['eq.devspace_clients']
    assert calls[2][2]['execution_service']==['eq.devspace_clients']


def test_denied_and_mixed_tenant_reads_cannot_be_ready():
    def denied(*args):raise HTTPReadError(403)
    assert probe_direct(CONTRACT,[ORG],ENV,denied)['connectivity_status']=='DEGRADED'
    def mixed(*args):return [{'id':'row','organization_id':'other'}]
    assert probe_direct(CONTRACT,[ORG],ENV,mixed)['connectivity_status']=='UNKNOWN'


def test_service_scopes_are_independent_of_domain_scope():
    now=1800000000
    report={'checked_at':timestamp(now),'organization_ids':[ORG], 'connectivity_status':'CONNECTED',
        'configuration_status':'VERIFIED','reads':{'intelligence_reports':{'status':'VERIFIED'}}}
    data={'collected_at':timestamp(now),'engines':[{'engine_id':'mmonolith', 'service_capabilities':{'devspace_clients':report}}],
        'trace_overview':{'matrix':[{'engine_id':'mmonolith','service_id':'devspace_clients','status':'UNKNOWN'}]}}
    result=project(data,{'organization_ids':['domain-org'],'service_organization_ids':{'devspace_clients':[ORG]}},now)
    assert result['trace_overview']['matrix'][0]['status']=='READY'

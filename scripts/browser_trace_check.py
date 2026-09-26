"""Browser-only trace fixture; never writes synthetic monitoring data."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from services.trace_service import normalize,project,overview
from adapters.base import timestamp
import time

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:5056',wait_until='networkidle')
    fixture=page.request.get('http://127.0.0.1:5056/api/status').json()
    now=time.time()
    run={'process_id':'browser-test','process_type':'domain','source':'dsorchestrator','organization_id':None,'correlation_id':'existing',
         'started_at':timestamp(now-50),'completed_at':timestamp(now),'last_activity':timestamp(now),'source_status':'FAILED','status':'FAILED','current_stage':'decision',
         'stages':[{'stage':stage,'engine':engine,'status':state,'started_at':timestamp(now-40),'completed_at':timestamp(now-10),'duration_seconds':30,'error':'<img src=x onerror=alert(1)>' if state=='FAILED' else None} for stage,engine,state in [('research','mmonolith','COMPLETED'),('decision','decision_engine','FAILED')]]}
    runs,events=normalize([run],{})
    fixture['traces']=[project(runs[0],events,{})]
    fixture['trace_overview']=overview(fixture['traces'],{})
    page.route('**/api/status',lambda route:route.fulfill(json=fixture))
    page.reload(wait_until='networkidle')
    page.locator('[data-tab="traces"]').click()
    assert page.locator('#trace-table tbody tr').count()==1
    page.locator('#trace-search').fill('browser-test')
    page.locator('#trace-table [data-trace]').click()
    assert 'CUT OFF AT: Decision Engine' in page.locator('#detail-body').inner_text()
    assert 'NOT_REACHED' in page.locator('#detail-body').inner_text()
    assert page.locator('#detail img').count()==0
    page.locator('#close-detail').click()
    page.locator('[data-tab="services"]').click()
    assert page.locator('#service-matrix .matrix-cell').count()==25
    page.locator('[data-cell-service="domain_merchant"][data-cell-engine="decision_engine"]').click()
    assert 'Current capability' in page.locator('#detail-body').inner_text()
    assert 'Recent activity — source timestamps' in page.locator('#detail-body').inner_text()
    page.get_by_role('button',name='View service pipeline →',exact=True).click()
    page.locator('#detail [data-edge-id="intelligence_read"]').click()
    assert 'UNKNOWN' in page.locator('#detail-body').inner_text()
    page.locator('#close-detail').click()
    page.locator('[data-cell-service="domain_merchant"][data-cell-engine="decision_engine"]').click()
    page.get_by_role('button',name='View failed trace →',exact=True).click()
    assert 'Last successful stage' in page.locator('#detail-body').inner_text()
    page.locator('#close-detail').click()
    page.locator('[data-tab="trace-engines"]').click()
    page.locator('#trace-engine-list [data-trace-engine="crm"]').click()
    assert page.locator('#detail').is_visible()
    page.locator('#close-detail').click()
    page.set_viewport_size({'width':390,'height':844})
    for tab in ('overview','traces','services','trace-engines','processes','errors','activity'):
        page.locator(f'[data-tab="{tab}"]').click()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),tab
    assert not errors,errors
    browser.close()
    print('Trace search, matrix drilldown, engine scope, full workflow, escaping and mobile layout passed.')

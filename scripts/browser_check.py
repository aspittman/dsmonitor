"""Optional browser validation against a running local dsmonitor instance."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:5055/',wait_until='networkidle')
    page.wait_for_selector('#engines .card')
    assert page.locator('#engines .card').count()==4
    assert page.locator('#infrastructure .card').count()==2
    page.screenshot(path=str(ROOT/'docs/dashboard-desktop.png'),full_page=True)
    page.locator('[data-engine="mmonolith"]').first.click()
    assert page.locator('#detail').is_visible()
    assert page.get_by_text('Why this status?',exact=True).is_visible()
    page.locator('#close-detail').click()
    for tab in ('processes','activity','errors','history','overview'):
        page.locator(f'[data-tab="{tab}"]').click()
        assert page.locator('#'+tab).is_visible()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(ROOT/'docs/dashboard-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    # Browser-only fixture verifies populated UI and HTML escaping. It is never sent
    # to the application or saved as operational/monitoring state.
    fixture=page.request.get('http://127.0.0.1:5055/api/status').json()
    fixture['organizations']=[{'id':'test-org','name':'Test business'}]
    fixture['processes']=[{
        'process_id':'fixture-run','process_type':'domain','display_name':'Fixture domain',
        'organization_id':'test-org','status':'FAILED','source_status':'FAILED',
        'current_stage':'execution','started_at':'2026-09-17T12:00:00Z',
        'last_activity':'2026-09-17T12:02:00Z','completed_at':None,'duration_seconds':None,
        'error_count':1,'last_error':'<img src=x onerror=alert(1)>',
        'correlation_id':'fixture-correlation','reason':'Browser-only test fixture',
        'lineage':[],'stages':[
            {'stage':'research','engine':'mmonolith','status':'COMPLETED',
             'started_at':'2026-09-17T12:00:00Z','completed_at':'2026-09-17T12:01:00Z',
             'duration_seconds':60,'retries':0,'error':None,'references':{}},
            {'stage':'execution','engine':'devspace_one','status':'FAILED',
             'started_at':'2026-09-17T12:01:00Z','completed_at':'2026-09-17T12:02:00Z',
             'duration_seconds':60,'retries':2,'error':'<img src=x onerror=alert(1)>','references':{}}
        ]
    }]
    page.route('**/api/status',lambda route:route.fulfill(json=fixture))
    page.set_viewport_size({'width':1440,'height':1100})
    page.reload(wait_until='networkidle')
    page.locator('[data-tab="processes"]').click()
    page.locator('#business-filter').select_option('test-org')
    page.locator('#engine-filter').select_option('devspace_one')
    assert page.locator('#process-table tbody tr').count()==1
    page.locator('#process-table [data-process="fixture-run"]').click()
    assert page.locator('#detail').is_visible()
    assert page.locator('#detail .stage').count()==2
    assert page.locator('#detail img').count()==0
    assert '<img src=x onerror=alert(1)>' in page.locator('#detail-body').inner_text()
    assert 'Retries: 2' in page.locator('#detail-body').inner_text()
    page.locator('#close-detail').click()
    page.locator('#type-filter').select_option('scholarship')
    assert page.locator('#process-table .empty').is_visible()
    assert not errors,errors
    print(json.dumps({'browser':'Chromium','engine_cards':4,'infrastructure_cards':2,'tabs':5,'detail_panel':'passed','mobile_overflow':False,'workflow_filters':'passed','failure_detail':'passed','html_escaping':'passed','javascript_errors':errors}))
    browser.close()

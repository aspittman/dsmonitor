"""Check live dashboard rendering and simulate lost updates in browser memory only."""
import copy
from datetime import datetime, timedelta, timezone
import json
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

for _ in range(20):
    try:
        with urlopen('http://127.0.0.1:5055/api/status', timeout=5) as response:
            live=json.load(response)
        if live.get('trace_overview',{}).get('matrix'):break
    except OSError:pass
    time.sleep(1)
else:raise RuntimeError('Monitor did not finish initial collection')
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:5055/',wait_until='networkidle')
    page.wait_for_selector('#engines .card')
    page.locator('[data-tab="services"]').click()
    page.wait_for_selector('#service-matrix .matrix-cell')
    assert 'Checked' in page.locator('#service-matrix').inner_text()
    page.locator('[data-cell-service="domain_merchant"][data-cell-engine="mmonolith"]').click()
    assert 'Current readiness' in page.locator('#detail').inner_text()
    assert 'Next action' in page.locator('#detail').inner_text()
    page.locator('#close-detail').click()
    # Synthetic status only in the browser, never written to monitoring or business storage.
    payload=copy.deepcopy(live)
    now=datetime.now(timezone.utc); expiry=(now+timedelta(seconds=3)).isoformat()
    payload.update(served_at=now.isoformat(),collected_at=now.isoformat())
    payload['monitor_freshness']={'status':'FRESH','checked_at':now.isoformat(),'expires_at':expiry}
    for row in payload['engines']+payload['trace_overview']['matrix']:
        if row.get('readiness',{}).get('status')=='NOT_CONFIGURED':continue
        row['status']='READY'
        row['readiness']={'status':'READY','checked_at':now.isoformat(),'expires_at':expiry}
    page.route('**/api/status',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(payload)))
    page.evaluate('refresh()')
    assert page.evaluate("() => state.engines[0].status") == "READY"
    page.unroute('**/api/status')
    page.route('**/api/status',lambda route:route.abort())
    for _ in range(20):
        if page.evaluate("() => state.engines[0].status") == "STALE":break
        page.wait_for_timeout(500)
    assert page.evaluate("() => state.engines[0].status") == "STALE"
    assert page.locator('#service-matrix').get_by_text('STALE',exact=True).count()>0
    assert not errors, errors
    browser.close()
print('Live UI and browser expiry after lost updates verified; no browser errors.')

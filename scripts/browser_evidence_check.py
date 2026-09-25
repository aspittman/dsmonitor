"""Disposable UI regression checks. Never runs collectors or writes operational state."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import threading
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from app import create_app
from config import load_config
from services.evidence_service import shared_state
from services.trace_service import normalize,project,overview
from services.process_service import crm_processes

ORG='11111111-1111-4111-8111-111111111111'
AT='2026-09-25T01:00:00+00:00'
with tempfile.TemporaryDirectory() as temp:
    config=load_config();config.update(database=str(Path(temp)/'monitor.db'),organization_ids=[ORG])
    app=create_app(config,start_collector=False)
    monitor=app.extensions['monitor']
    contexts={ORG:{'_observed_at':AT,'intelligence_reports':[{'id':'report','organization_id':ORG,'report_type':'DOMAIN_MARKET','created_at':AT,'metadata':{'private_body':'PRIVATE PAYLOAD'}}]}}
    processes=crm_processes(contexts,[])
    processes.append({'process_id':'decision:one:domain','process_type':'domain','display_name':'Domain evaluation','source':'decision_log','organization_id':ORG,'status':'UNKNOWN','stages':[], 'lineage':[], 'last_activity':None,'reason':'Untimestamped log','error_count':0,'current_stage':'decision'})
    runs,events=normalize(processes,{})
    traces=[project(r,[e for e in events if e['trace_id']==r['trace_id']],{}) for r in runs]
    fixture={**monitor.data,'collected_at':AT,'processes':processes,'traces':traces,'trace_overview':overview(traces,{}),
             'shared_state':shared_state(contexts,config,processes),'organizations':[{'id':ORG,'name':'Fixture organization'}]}
    fixture['engines']=[{'engine_id':e,'display_name':name,'infrastructure':e in ('crm','supabase'),'status':'UNKNOWN','availability':'UNKNOWN','checks':[],'monitoring_issue':None} for e,name in [('mmonolith','MMonolith'),('decision_engine','Decision Engine'),('devspace_one','DevSpace One'),('dsorchestrator','dsorchestrator'),('crm','CRM'),('supabase','Supabase')]]
    monitor.data=fixture
    server=make_server('127.0.0.1',0,app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
            page.locator('[data-tab="traces"]').click()
            assert '0 workflows with a shared run ID' in page.locator('#trace-source-summary').inner_text()
            assert 'Stored research report' in page.locator('#trace-table').inner_text()
            assert 'Decision Engine log' in page.locator('#trace-table').inner_text()
            assert 'Not timestamped in source' in page.locator('#trace-table').inner_text()
            assert 'WORKFLOW NOT TRACKED' in page.locator('#trace-table').inner_text()
            page.locator('#trace-table [data-trace]').first.click()
            assert 'Read from:' in page.locator('#detail-body').inner_text()
            page.locator('#close-detail').click()
            page.locator('[data-tab="shared-state"]').click()
            assert 'intelligence_reports' in page.locator('#shared-content').inner_text()
            assert 'PRIVATE PAYLOAD' not in page.content()
            page.locator('[data-shared-record]').first.click()
            assert 'CRM API read-back of Supabase' in page.locator('#detail-body').inner_text()
            page.locator('#close-detail').click()
            page.set_viewport_size({'width':390,'height':844})
            for tab in ('traces','processes','shared-state','services'):
                page.locator(f'[data-tab="{tab}"]').click()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),tab
            assert not errors,errors
            browser.close()
        print('Evidence source labels, missing times, CRM record details, payload exclusion and mobile layout passed.')
    finally: server.shutdown();thread.join()

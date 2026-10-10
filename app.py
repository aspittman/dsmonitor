"""Read-only local dashboard. There are no operational mutation routes."""
from flask import Flask, jsonify, render_template, request, abort
from config import load_config
from services.monitor import Monitor
import ds_usage
ds_usage.install()


def create_app(config=None, start_collector=True):
    settings=config or load_config()
    if settings.get("crm_url"):
        import os
        os.environ.setdefault("CRM_BASE_URL", settings["crm_url"])
    app=Flask(__name__)
    monitor=Monitor(settings)
    app.extensions['monitor']=monitor

    @app.before_request
    def local_only():
        # Blocks DNS rebinding and accidental reverse-proxy exposure.
        if request.host.split(':')[0] not in ('localhost','127.0.0.1') or request.remote_addr not in ('127.0.0.1','::1',None): abort(403)
        if request.method not in ('GET','HEAD'): abort(405)

    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['Referrer-Policy']='no-referrer'
        return response

    @app.get('/')
    def index(): return render_template('index.html', refresh=settings['refresh_seconds'])

    @app.get('/api/status')
    def status(): return jsonify(monitor.snapshot())

    @app.get('/api/consumption')
    def consumption():
        try:
            raw=request.args.get('days','7')
            if raw not in ('1','7','30'): return jsonify({'error':'Choose 1, 7, or 30 days'}),400
            days=int(raw)
            data=ds_usage.summary(days)
            infrastructure=next((e for e in monitor.snapshot().get('engines',[]) if e.get('engine_id')=='supabase'),{})
            data['database_overview']=infrastructure.get('database_overview')
            return jsonify(data)
        except Exception:
            return jsonify({'error':'Local consumption accounting unavailable'}),503

    @app.get('/api/diagnostics')
    def diagnostics():
        from services.domain_diagnostic import recent_reports
        from services.security import Sanitizer
        from config import ROOT
        rows = recent_reports(settings.get('diagnostic_dir', ROOT / 'data/diagnostics'), settings.get('organization_ids', []))
        return jsonify(Sanitizer(settings.get('secrets', [])).clean(rows))

    @app.get('/api/history')
    def history():
        try: return jsonify(monitor.store.history('events' if request.args.get('kind')=='events' else 'snapshots'))
        except Exception: return jsonify({'error':'Monitoring history unavailable'}),503

    @app.get('/api/traces')
    def traces():
        data=monitor.snapshot()
        rows=data.get('traces', [])
        for field in ('service_id','organization_id','status'):
            if request.args.get(field): rows=[r for r in rows if r.get(field)==request.args[field]]
        for field in ('engine_id','stage'):
            if request.args.get(field): rows=[r for r in rows if any(s.get(field)==request.args[field] for s in r['stages'])]
        for query,field in (('failed_engine','engine_id'),('failed_stage','stage')):
            if request.args.get(query): rows=[r for r in rows if (r.get('root_failure') or {}).get(field)==request.args[query]]
        if request.args.get('q'):
            query=request.args['q'].lower()
            rows=[r for r in rows if query in str((r['workflow_run_id'],r['source_run_id'],r['service_id'],r['organization_id'],r.get('correlation_id'),[(e.get('error_message')) for e in r['events']])).lower()]
        for param,op in (('from',lambda a,b:a>=b),('to',lambda a,b:a<=b)):
            if request.args.get(param):
                from adapters.base import epoch
                bound=epoch(request.args[param])
                if bound is None: return jsonify({'error':'Invalid date filter'}),400
                rows=[r for r in rows if epoch(r.get('started_at')) is not None and op(epoch(r['started_at']),bound)]
        return jsonify({'runs':rows,'overview':data.get('trace_overview',{}),'collected_at':data['collected_at']})

    @app.get('/api/traces/<trace_id>')
    def trace_detail(trace_id):
        row=next((r for r in monitor.snapshot().get('traces',[]) if r['trace_id']==trace_id),None)
        return jsonify(row) if row else (jsonify({'error':'Trace not in retained monitoring window'}),404)

    @app.get('/healthz')
    def health():
        data=monitor.snapshot()
        fresh=data['monitor_freshness']['status']=='FRESH'
        return jsonify({'status':'ONLINE' if fresh else data['monitor_freshness']['status'], 'application':'dsmonitor','collected_at':data['collected_at']}), 200 if fresh else 503

    if start_collector: monitor.start()
    return app


if __name__=='__main__':
    config=load_config()
    create_app(config).run(host='127.0.0.1',port=config['port'],debug=False,use_reloader=False)

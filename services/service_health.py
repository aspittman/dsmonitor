"""Read-only, explainable Services projections. No operational calls or mutations.

Current engine capability must be engine-scoped. A monitor credential is never
silently treated as an engine credential. Missing/bounded evidence stays unknown.
"""
from collections import Counter
from datetime import datetime, timezone
from adapters.base import epoch, timestamp
from service_registry import registry, identify

def fresh(at, now, ttl):
    value = epoch(at)
    return value is not None and 0 <= now - value <= ttl


def scoped_records(contexts, definitions):
    """Assign service only via explicit identity, known type, or same-tenant FK."""
    records = []
    links = {'recommendation_evidence': ('recommendations', 'recommendation_id'),
             'execution_requests': ('recommendations', 'recommendation_id'),
             'execution_results': ('execution_requests', 'execution_request_id'),
             'feedback_evaluations': ('execution_results', 'execution_result_id')}
    for org, ctx in contexts.items():
        index = {}
        tables = list(dict.fromkeys(('intelligence_reports', 'recommendations', *links, *ctx)))
        for table in tables:
            rows = ctx.get(table, [])
            if not isinstance(rows, list): continue
            for row in rows:
                if not isinstance(row, dict): continue
                if row.get('organization_id') != org or not row.get('id'): continue
                service = identify(row.get('service_id'), definitions)
                if not service and (row.get('report_type') == 'DOMAIN_MARKET' or str(row.get('recommendation_type', '')).startswith('DOMAIN_')):
                    service = 'domain_merchant'
                if not service and row.get('execution_service') in ('devspace_outreach', 'apollo_outreach'):
                    service = 'devspace_services'
                parent = None
                if table in links:
                    parent_table, fk = links[table]
                    parent = index.get((parent_table, row.get(fk)))
                    if parent:
                        if service and service != parent['service_id']: continue
                        service = parent['service_id']
                if table=='recommendation_evidence' and not service:
                    report = index.get(('intelligence_reports', row.get('intelligence_report_id')))
                    consumer_exists = any(r.get('id')==row.get('recommendation_id') and r.get('organization_id')==org for r in ctx.get('recommendations', []))
                    if report and consumer_exists:
                        # A legacy NO_ACTION recommendation can explicitly use
                        # a report without declaring its own canonical service.
                        service = report['service_id']
                if not service: continue
                record = dict(row, table=table, service_id=service, observed_at=ctx.get('_observed_at'))
                index[(table, row['id'])] = record
                records.append(record)
    return records


def pipeline(service, spec, records, runs, config, now):
    edges = []
    relevant = [r for r in records if r['service_id'] == service]
    receipts = [e for r in runs if r['service_id']==service for e in r.get('events', [])
                if e.get('event_type')=='read_succeeded' and e.get('status')=='COMPLETED'
                and e.get('metadata', {}).get('record_id') and e.get('metadata', {}).get('table')]
    latest = max((r for r in runs if r['service_id'] == service), key=lambda r: epoch(r.get('last_activity')) or 0, default={})
    for contract in spec.get('handoffs', []):
        items = []
        threshold = config.get('trace_thresholds', {}).get(service, {}).get('handoffs', {}).get(contract['id'], {}).get('stalled_seconds')
        for row in relevant:
            if row['table'] != contract['table']: continue
            at = timestamp(row.get('completed_at') or row.get('created_at'))
            state, reason, consumed_at = 'UNKNOWN', 'No explicit downstream receipt in bounded CRM context.', None
            refs = [{'table': row['table'], 'id': row['id']}]
            if not contract.get('consumer_table'):
                state, reason, consumed_at = 'CONFIRMED', 'Real output exists in CRM shared state; persistence confirmed, current writer permissions unverified.', at
            else:
                matches = [r for r in relevant if r['table'] == contract['consumer_table'] and r['organization_id'] == row['organization_id'] and r.get(contract['foreign_key']) == row['id']]
                if matches:
                    state, reason = 'CONFIRMED', 'Same-organization downstream record explicitly references this source ID.'
                    consumed_at = max((timestamp(r.get('created_at')) or '' for r in matches), default='') or None
                    refs += [{'table': r['table'], 'id': r['id'], 'field': contract['foreign_key']} for r in matches]
                elif any(e['engine_id']==contract['to'] and e.get('organization_id')==row['organization_id']
                         and e['metadata']['table']==row['table'] and e['metadata']['record_id']==row['id'] for e in receipts):
                    receipt = max((e for e in receipts if e['engine_id']==contract['to'] and e.get('organization_id')==row['organization_id'] and e['metadata']['table']==row['table'] and e['metadata']['record_id']==row['id']), key=lambda e: epoch(e.get('timestamp')) or 0)
                    state, reason, consumed_at = 'CONFIRMED', 'Explicit engine read receipt references the same tenant, table and record ID.', receipt.get('timestamp')
                    refs.append({'trace_id': receipt['trace_id'], 'event_id': receipt['trace_event_id'], 'workflow_run_id': receipt.get('workflow_run_id')})
                elif contract.get('approval_required') and not (row.get('approved_at') and row.get('approved_by')):
                    state, reason = 'NOT_EXPECTED', 'No verified approval; pickup is not expected.'
                elif row.get('status') in contract.get('receipt_statuses', []):
                    state, reason = 'CONFIRMED', 'Durable request state proves the registered claim protocol consumed this request ID.'
                    consumed_at = timestamp(row.get(contract.get('receipt_timestamp', 'updated_at')))
                elif row.get('status') in ('CANCELLED', 'REJECTED', 'SKIPPED'):
                    state, reason = 'NOT_EXPECTED', 'Source work is cancelled, rejected or skipped.'
                elif row.get('status') == 'FAILED':
                    state, reason = 'FAILED', 'Source work explicitly reports an unresolved failure.'
                elif threshold and epoch(at) is not None:
                    age = now - epoch(at)
                    state = 'LATE' if age > threshold else 'PENDING'
                    reason = f'No receipt in bounded context for {row["id"]}; age {max(0, int(age))}s; configured pickup threshold {threshold}s. Absence is not proof of non-consumption.'
            items.append({'status': state, 'reason': reason, 'source_at': at, 'consumed_at': consumed_at,
                          'observed_at': row.get('observed_at'), 'organization_id': row['organization_id'],
                          'is_test': row.get('is_test'),
                          'workflow_run_id': row.get('workflow_run_id'), 'references': refs})
        # Any outstanding obligation wins over successful unrelated traffic.
        rank = {'FAILED': 0, 'LATE': 1, 'PENDING': 2, 'UNKNOWN': 3, 'CONFIRMED': 4, 'NOT_EXPECTED': 5}
        items.sort(key=lambda x: (rank[x['status']], -(epoch(x['source_at']) or 0)))
        focus = items[0] if items else None
        state = focus['status'] if focus else 'UNKNOWN'
        reason = focus['reason'] if focus else 'No attributable source record / receipt exposed in the monitored scope.'
        if not items and contract.get('stage') and any(s['stage'] == contract['stage'] for s in latest.get('downstream_not_reached', [])):
            state, reason = 'NOT_REACHED', 'Latest workflow stopped upstream before this producer.'
        edges.append({**contract, 'status': state, 'reason': reason, 'threshold_seconds': threshold,
                      'evidence': items, 'trace_id': latest.get('trace_id') if latest.get('workflow_run_id') and any(i.get('workflow_run_id') == latest['workflow_run_id'] for i in items) else None})
        edges[-1]['trace_ids'] = sorted({r['trace_id'] for r in runs if r['service_id']==service and r.get('workflow_run_id') and any(i.get('workflow_run_id')==r['workflow_run_id'] and i['organization_id']==r.get('organization_id') for i in items)} | {ref['trace_id'] for i in items for ref in i['references'] if ref.get('trace_id')})
    return edges


def activity(spec, thresholds, runs, engine, now):
    expectation = {**spec.get('activity', {}), **thresholds.get('activity', {})}
    interval = expectation.get('expected_interval')
    anchor = epoch(expectation.get('anchor_at'))
    starts = [epoch(r.get('started_at')) for r in runs if r.get('workflow_run_id') and any(s['engine_id'] == engine and s.get('observed') for s in r['stages'])]
    actual = max((x for x in starts if x is not None), default=None)
    active = any(s['status'] in ('RUNNING', 'STALLED') for r in runs for s in r['stages'] if s['engine_id'] == engine)
    waiting = any(r['status'] in ('WAITING', 'WAITING_FOR_APPROVAL') for r in runs)
    result = {'activity_status': 'ACTIVE' if active else 'WAITING' if waiting else 'UNKNOWN',
              'expected_activity': expectation or 'UNKNOWN', 'last_actual_run': timestamp(actual),
              'last_expected_run': None, 'next_expected_activity': None, 'late_by_seconds': 0}
    if not interval or interval <= 0: return result
    grace = expectation.get('late_threshold', 0)
    if anchor is not None:
        due = anchor + int((now-anchor)//interval)*interval if now >= anchor else None
        next_due = due + interval if due is not None else anchor
    elif actual is not None:
        due = actual + interval if now >= actual + interval else None
        next_due = actual + interval
    else:
        return result  # No guessed first due date.
    late = max(0, now-due-grace) if due is not None and (actual is None or actual < due) else 0
    result.update(last_expected_run=timestamp(due), next_expected_activity=timestamp(next_due), late_by_seconds=late,
                  activity_status='LATE' if late and not waiting else 'ACTIVE' if active else 'WAITING' if waiting else 'IDLE')
    return result


def capability(engine, service, contract, engines, contexts, config, now):
    ttl = config.get('capability_seconds', 60)
    evidence, dependencies = [], []
    reported = engine.get('service_capabilities', {}).get(service, {})
    valid = fresh(reported.get('checked_at'), now, ttl) and set(config.get('organization_ids', [])) <= set(reported.get('organization_ids', []))
    for dep in contract.get('dependencies', []):
        source = engines.get(dep, {})
        checks = source.get('checks', [])
        offline = any(c['status'] == 'OFFLINE' for c in checks)
        status = ('DISCONNECTED' if offline else 'UNKNOWN' if source.get('dependency_status')=='UNKNOWN'
                  else 'DEGRADED' if any(c['status'] == 'ERROR' for c in checks)
                  else 'CONNECTED' if source.get('status') == 'HEALTHY' else 'UNKNOWN')
        dependencies.append({'dependency': dep, 'status': status, 'scope': 'monitor vantage point',
                             'observed_at': source.get('observed_at'), 'checks': checks})
    connectivity = 'UNKNOWN'
    if any(d['status'] == 'DISCONNECTED' for d in dependencies): connectivity = 'DISCONNECTED'
    elif any(d['status'] == 'DEGRADED' for d in dependencies): connectivity = 'DEGRADED'
    if valid and reported.get('connectivity_status') in ('CONNECTED', 'DISCONNECTED', 'DEGRADED', 'UNKNOWN'):
        # An engine's explicit check is authoritative for its own network vantage.
        connectivity = reported['connectivity_status']
    read = 'UNKNOWN'
    read_checks = []
    for table in contract.get('inputs', []):
        receipt = reported.get('reads', {}).get(table, {}) if valid else {}
        status = receipt.get('status') if receipt.get('status') in ('VERIFIED', 'FAILED') else 'UNKNOWN'
        reason = receipt.get('reason') or 'No fresh read result from this engine; monitor access does not prove engine permission.'
        if engine.get('engine_id') == 'crm' and contexts and all(isinstance(ctx.get(table), list) and fresh(ctx.get('_observed_at'), now, config.get('crm_context_seconds', 120)+config.get('refresh_seconds', 10)) for ctx in contexts.values()) and set(contexts) == set(config.get('organization_ids', [])):
            status, reason = 'VERIFIED', 'Authenticated tenant-scoped CRM context returned this table (zero rows is valid); scope is monitoring API access.'
        read_checks.append({'table': table, 'status': status, 'reason': reason})
    if read_checks:
        read = 'FAILED' if any(c['status'] == 'FAILED' for c in read_checks) else 'VERIFIED' if all(c['status'] == 'VERIFIED' for c in read_checks) else 'UNKNOWN'
    if engine.get('engine_id') == 'crm' and engine.get('status') == 'HEALTHY' and read == 'VERIFIED':
        connectivity = 'CONNECTED'  # API's own DB-backed table reads, not frontend HTTP.
    if connectivity == 'DISCONNECTED': read = 'UNAVAILABLE'
    evidence.append({'dimension': 'connectivity', 'status': connectivity, 'reason': reported.get('reason') if valid else 'Engine-scoped check unavailable. Shared dependency observations are shown separately.', 'observed_at': reported.get('checked_at') if valid else None})
    if engine.get('engine_id')=='crm' and connectivity=='CONNECTED' and read=='VERIFIED':
        evidence[-1].update(reason='Authenticated CRM API returned every required table in the configured tenant scope; database-backed access verified.',
                            observed_at=min((ctx.get('_observed_at') or '' for ctx in contexts.values()), default=None))
    evidence.extend({'dimension': 'read', **c, 'observed_at': reported.get('checked_at') if valid else min((ctx.get('_observed_at') or '' for ctx in contexts.values()), default=None) if c['status']=='VERIFIED' else None} for c in read_checks)
    return connectivity, read, reported if valid else {}, dependencies, evidence


def upgrade(overview, runs, engines, contexts, config, now=None):
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    definitions = registry(config)
    by_engine = {e['engine_id']: e for e in engines}
    records = scoped_records(contexts, definitions)
    identities = {(r['organization_id'], r['table'], r['id']) for r in records}
    for run in runs:
        for event in run.get('events', []):
            meta = event.get('metadata', {})
            table, rid = meta.get('table'), meta.get('record_id')
            outputs = definitions.get(run['service_id'], {}).get('engines', {}).get(event['engine_id'], {}).get('outputs', [])
            identity = (run.get('organization_id'), table, rid)
            if event.get('event_type')=='write_persisted' and event['status']=='COMPLETED' and table in outputs and rid and identity not in identities:
                records.append({'organization_id': run.get('organization_id'), 'table': table, 'id': rid,
                                'service_id': run['service_id'], 'created_at': event.get('timestamp'),
                                'workflow_run_id': run.get('workflow_run_id'), 'observed_at': run.get('observed_at')})
                identities.add(identity)
    flows = {s: pipeline(s, spec, records, runs, config, now) for s, spec in definitions.items()}
    for cell in overview['matrix']:
        service, eid = cell['service_id'], cell['engine_id']
        spec = definitions.get(service, {})
        contract = spec.get('engines', {}).get(eid, {})
        relevant = [r for r in runs if r['service_id'] == service]
        configured = eid in spec.get('engines', {}) or any(s['engine_id'] == eid for s in spec.get('stages', [])) or spec.get('coordinator') == eid or cell['observed_runs'] > 0
        engine = by_engine.get(eid, {'engine_id': eid})
        connection, read, report, deps, evidence = capability(engine, service, contract, by_engine, contexts, config, now)
        outputs = [r for r in records if r['service_id'] == service and r['table'] in contract.get('outputs', [])]
        writes = [timestamp(r.get('created_at')) for r in outputs if timestamp(r.get('created_at'))]
        last_write = max(writes, default=None)
        write = 'UNVERIFIED'
        write_ttl = contract.get('write_evidence_seconds', config.get('write_evidence_seconds', 86400))
        persisted = [e for r in relevant for e in r.get('events', []) if e['engine_id']==eid
                     and e.get('event_type')=='write_persisted' and e['status']=='COMPLETED'
                     and e.get('metadata', {}).get('table') in contract.get('outputs', []) and e.get('metadata', {}).get('record_id')]
        last_write = max([at for at in [last_write]+[timestamp(e.get('timestamp')) for e in persisted] if at], default=None)
        required_orgs = set(config.get('organization_ids', []))
        verified_pairs = {(r.get('organization_id'), r['table']) for r in outputs if fresh(r.get('created_at'), now, write_ttl)}
        verified_pairs.update((e.get('organization_id'), e['metadata']['table']) for e in persisted if fresh(e.get('timestamp'), now, write_ttl))
        if contract.get('outputs') and required_orgs and all((org, table) in verified_pairs for org in required_orgs for table in contract['outputs']): write = 'VERIFIED'
        if report.get('write_status') in ('VERIFIED', 'FAILED', 'UNVERIFIED'): write = report['write_status']
        write_failures = [e for r in relevant for e in r.get('events', []) if e['engine_id']==eid
                          and e.get('event_type')=='write_persisted' and e['status']=='FAILED'
                          and e.get('metadata', {}).get('table') in contract.get('outputs', [])
                          and fresh(e.get('timestamp'), now, write_ttl)]
        unresolved_writes = [e for e in write_failures if not any(p['metadata']['table']==e['metadata']['table'] and p.get('organization_id')==e.get('organization_id') and (epoch(p.get('timestamp')) or 0)>(epoch(e.get('timestamp')) or 0) for p in persisted)]
        if unresolved_writes: write = 'FAILED'
        if connection == 'DISCONNECTED': write = 'UNAVAILABLE'
        evidence.append({'dimension': 'write', 'status': write, 'source_at': last_write,
                         'observed_at': report.get('checked_at') or max((r.get('observed_at') or '' for r in outputs), default=None),
                         'reason': 'Recent real persistence or fresh engine capability required for every registered output. Credentials alone never verify writes.',
                         'references': [{'table': r['table'], 'id': r['id'], 'source_at': timestamp(r.get('created_at'))} for r in outputs] + [{'table': e['metadata']['table'], 'id': e['metadata']['record_id'], 'trace_id': e['trace_id'], 'source_at': e['timestamp']} for e in persisted]})
        evidence.extend({'dimension':'write', 'status':'FAILED', 'source_at':e.get('timestamp'),
                         'reason':'Explicit persistence failure; no later successful persistence receipt for this tenant/table.',
                         'references':[{'trace_id':e['trace_id'], 'table':e['metadata']['table']}]} for e in unresolved_writes)
        edges = [e for e in flows.get(service, []) if eid in (e['from'], e['to'])]
        handoff = next((s for s in ('FAILED', 'LATE', 'PENDING', 'UNKNOWN', 'NOT_REACHED', 'CONFIRMED', 'NOT_EXPECTED') if any(e['status'] == s for e in edges)), 'UNKNOWN')
        # Failure is unresolved within its own workflow. Unrelated later success
        # never erases it. Explicit successful child retry can resolve a parent.
        recovered_parents = {(r.get('organization_id'), r.get('parent_run_id')) for r in relevant if r['status'] == 'COMPLETED' and r.get('parent_run_id')}
        failures = [r for r in relevant if r.get('root_failure') and r['root_failure']['engine_id'] == eid and (r.get('organization_id'), r.get('workflow_run_id')) not in recovered_parents]
        latest = max(relevant, key=lambda r: epoch(r.get('last_activity')) or 0, default={})
        blocked = any(s['engine_id'] == eid for s in latest.get('downstream_not_reached', [])) and not any(s['engine_id'] == eid and s.get('observed') and s['status'] not in ('NOT_STARTED', 'NOT_REACHED') for s in latest.get('stages', []))
        workflow = 'FAILED' if failures else 'NOT_REACHED' if blocked else 'WAITING' if any(r['status'] in ('WAITING', 'WAITING_FOR_APPROVAL') for r in relevant) else 'CLEAR'
        thresholds = config.get('trace_thresholds', {}).get(service, {}).get(eid, {})
        schedule_spec = dict(contract)
        if spec.get('expected_activity_seconds') and 'activity' not in schedule_spec:
            schedule_spec['activity'] = {'expected_interval': spec['expected_activity_seconds']}
        schedule = activity(schedule_spec, thresholds, relevant, eid, now)
        if report.get('work_expected') is False and schedule['activity_status']=='UNKNOWN':
            schedule.update(activity_status='IDLE', expected_activity='Engine reports no work due')
        stalled = any(s['engine_id'] == eid and s['status'] == 'STALLED' for r in relevant for s in r['stages'])
        capable = connection == 'CONNECTED' and read == 'VERIFIED' and write == 'VERIFIED'
        if not configured:
            overall, reason = ('NOT_CONFIGURED', spec.get('note', 'No registered participation or observed implementation.')) if service in definitions else ('UNKNOWN', 'Unregistered service; engine participation is unknown.')
        elif connection == 'DISCONNECTED': overall, reason = 'DISCONNECTED', 'Required dependency is unreachable: ' + ', '.join(d['dependency'] for d in deps if d['status']=='DISCONNECTED') if any(d['status']=='DISCONNECTED' for d in deps) else 'Engine reports its required dependency is unreachable.'
        elif failures: overall, reason = 'FAILED', 'Unresolved workflow failure in this engine: ' + str(failures[0].get('workflow_run_id') or failures[0]['source_run_id'])
        elif blocked: overall, reason = 'NOT_REACHED', 'Latest workflow stopped upstream before this engine.'
        elif connection == 'DEGRADED' or read == 'FAILED' or write == 'FAILED' or handoff in ('FAILED', 'LATE') or schedule['activity_status'] == 'LATE' or stalled:
            issues = (['Dependency authentication/API probe impaired'] if connection == 'DEGRADED' else []) + (['Required read denied or failed'] if read == 'FAILED' else []) + (['Write capability failed'] if write == 'FAILED' else []) + [e['reason'] for e in edges if e['status'] in ('LATE', 'FAILED')] + (['Expected workflow missing beyond configured grace period'] if schedule['activity_status']=='LATE' else []) + (['Workflow exceeded configured stage threshold'] if stalled else [])
            overall, reason = 'DEGRADED', '; '.join(issues)
        elif capable and schedule['activity_status'] == 'IDLE' and handoff not in ('PENDING',): overall, reason = 'IDLE', 'Dependencies and required reads verified; write evidence valid; no work currently due under the configured schedule.'
        elif capable and handoff in ('CONFIRMED', 'NOT_EXPECTED') and schedule['activity_status'] != 'WAITING': overall, reason = 'HEALTHY', 'Dependencies and required reads verified; writes evidenced; registered data flow confirmed or explicitly not expected; no unresolved failure.'
        else: overall, reason = 'UNKNOWN', 'Insufficient current capability / flow evidence: ' + ', '.join(f'{k}={v}' for k,v in [('connectivity',connection),('read',read),('write',write),('handoff',handoff),('activity',schedule['activity_status'])])
        last_handoff = max((i['consumed_at'] for e in edges for i in e['evidence'] if i['status']=='CONFIRMED' and i.get('consumed_at')), default=None)
        last_read = max([at for at in [timestamp(report.get('last_read'))] + [timestamp(e.get('timestamp')) for r in relevant for e in r.get('events', []) if e['engine_id']==eid and e.get('event_type')=='read_succeeded' and e['status']=='COMPLETED'] if at], default=None)
        evidence.append({'dimension': 'workflow', 'status': workflow, 'observed_at': timestamp(now),
                         'reason': 'Unresolved failures in retained, scoped workflow evidence; unrelated success does not erase a failure.',
                         'references': [{'trace_id': r['trace_id'], 'workflow_run_id': r.get('workflow_run_id')} for r in failures]})
        evidence.append({'dimension': 'activity', 'status': schedule['activity_status'], 'observed_at': timestamp(now),
                         'reason': 'Derived locally from explicitly configured interval/anchor and grace; unknown schedule incurs no inactivity penalty.',
                         'references': [schedule]})
        cell.update(status=overall, overall_status=overall, reason=reason, connectivity_status=connection,
                    read_status=read, write_status=write, handoff_status=handoff, workflow_status=workflow,
                    last_read=last_read, last_write=last_write, last_handoff=last_handoff,
                    last_verified_write=last_write if write=='VERIFIED' else None,
                    dependencies=deps, evidence=evidence, handoffs=edges, observed_at=timestamp(now),
                    latest_run=cell.get('latest_run') or latest.get('trace_id'),
                    failed_traces=[r['trace_id'] for r in failures], **schedule)
        cell['last_activity'] = max((at for at in (cell.get('last_activity'), last_read, last_write, last_handoff) if at), default=None)
    overview['pipelines'] = flows
    overview['health_summary'] = dict(Counter(c['status'] for c in overview['matrix']))
    overview['pipeline_problems'] = [{'service_id': s, 'edge_id': e['id'], 'status': e['status'], 'reason': e['reason']} for s, edges in flows.items() for e in edges if e['status'] in ('LATE', 'FAILED')]
    return overview

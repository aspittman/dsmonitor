"""Isolated engine bridge; invoked only by domain_diagnostic.py, never the dashboard."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys


def execute(request):
    context = request['context']
    org = context['organization_id']
    if request['stage'] == 'research':
        from services.domain_intelligence import discover
        from services.domain_intelligence.client import LoopClient
        args = request['args']
        class CorrelatedClient(LoopClient):
            def publish(self, organization_id, bundle, **kwargs):
                return super().publish(organization_id, bundle, workflow_context=context)
        discover.LoopClient = CorrelatedClient
        sys.argv = ['discover', *args, '--sync-crm']
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            discover.main()
        receipt = json.loads(output.getvalue().splitlines()[-1])
        bundle = json.loads(Path(receipt['path']).read_text())
        client = LoopClient(os.environ['CRM_BASE_URL'], os.environ['BOT_API_SECRET'])
        report_id = receipt['intelligence_report_id']
        stored = client.context(org)
        persisted = any(r['id'] == report_id for r in stored.get('intelligence_reports', []))
        metadata = bundle['report']['metadata']
        return {**receipt, 'intelligence_report_id': report_id, 'crm_readback': persisted,
                'candidate_count': len(metadata['candidates']),
                'observed_at': metadata.get('observed_at')}
    if request['stage'] == 'decision':
        from decision_engine.clients.crm_client import CRMClient
        from decision_engine.config.settings import CRMSettings, scoring_config
        from decision_engine.repositories.crm import CRMRepository
        from decision_engine.services.decision_service import DecisionService
        settings = CRMSettings.from_env()
        config = scoring_config(os.getenv('DECISION_SCORING_FILE') or None)
        evidence = {}

        class ObservedRepository(CRMRepository):
            def context(self, organization_id):
                result = super().context(organization_id)
                evidence['consumed_report_ids'] = [r['id'] for r in result.profile.get('domain_reports', [])]
                evidence['capabilities'] = [r for r in result.profile.get('execution_capability_details', [])
                                            if r.get('service_key') == 'domain_merchant']
                return result

            def finish_run(self, run_id, organization_id, recommendations, snapshot, summary, partial):
                result = super().finish_run(run_id, organization_id, recommendations, snapshot, summary, partial)
                evidence['summary'] = summary
                evidence['persisted'] = True
                return result

        repo = ObservedRepository(CRMClient(settings.api_url, settings.api_secret), config)
        result = DecisionService(repo, config).run(org, 'MANUAL_REQUEST', workflow_context=context)
        return {'run_id': result['run_id'], 'status': result['status'], **evidence}
    if request['stage'] == 'readiness':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scripts.capability_probe import probe
        profile = json.loads((Path.cwd() / 'monitoring/profile.json').read_text())
        return probe(profile, [org])['service_capabilities']['domain_merchant']
    raise ValueError('Unknown diagnostic stage')


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.read())
        result = execute(request)
        print(json.dumps({'ok': True, 'result': result}))
    except Exception as exc:
        # Never persist raw transport errors or credentials.
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__}))
        sys.exit(1)

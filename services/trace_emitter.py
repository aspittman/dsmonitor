"""Optional dependency-free source helper. Pass existing context through boundaries.

Copy this module into an engine or load it explicitly; never import dsmonitor's app.
An unavailable monitoring sink returns False and cannot fail business execution.
"""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4


def new_context(service_id, *, workflow_run_id=None, organization_id=None, parent_run_id=None, correlation_id=None):
    """Call ONLY at work creation, never at an engine boundary or retry."""
    return dict(workflow_run_id=workflow_run_id or str(uuid4()), service_id=service_id,
                organization_id=organization_id, parent_run_id=parent_run_id, correlation_id=correlation_id)


def trace_event(path, context, *, engine_id, stage, event_type, status, attempt=1, duration_ms=None, error_type=None):
    # Deliberately exclude arbitrary payloads, exception text, credentials and metadata.
    try:
        if not context.get('workflow_run_id') or not context.get('service_id'): return False
        event = {k:context.get(k) for k in ('workflow_run_id','service_id','organization_id','parent_run_id','correlation_id')}
        event.update(trace_event_id=str(uuid4()),engine_id=engine_id,stage=stage,event_type=event_type,
                     status=status,attempt=attempt,duration_ms=duration_ms,error_type=error_type,
                     timestamp=datetime.now(timezone.utc).isoformat())
        payload = (json.dumps(event,allow_nan=False)+'\n').encode()
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NONBLOCK,0o600)
        try: os.write(fd,payload)
        finally: os.close(fd)
        return True
    except Exception:
        return False

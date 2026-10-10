"""Local, warning-only thresholds for instrumented traffic; never provider quotas."""
import json
from pathlib import Path

DEFAULTS = {'daily_process_bytes':20*1024*1024, 'daily_process_requests':1000,
            'large_response_bytes':1024*1024}

def evaluate(processes):
    thresholds = dict(DEFAULTS)
    try:
        configured=json.loads((Path(__file__).resolve().parent/'data/usage-thresholds.json').read_text())
        thresholds.update({k:v for k,v in configured.items() if k in DEFAULTS and type(v) is int and v>0})
    except (OSError, ValueError, AttributeError):
        pass
    alerts=[]
    for row in processes:
        reasons=[]
        if row['bytes']>=thresholds['daily_process_bytes']:
            reasons.append('Daily measured transfer crossed the process warning threshold')
        if row['requests']>=thresholds['daily_process_requests']:
            reasons.append('Daily request count crossed the process warning threshold')
        if row['largest_response_bytes']>=thresholds['large_response_bytes']:
            reasons.append('A large response was downloaded today')
        if reasons:
            alerts.append({**row,'reasons':reasons})
    return alerts, thresholds

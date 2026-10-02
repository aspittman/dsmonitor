'use strict';
// Also expires a successful payload if the server or collector stops answering.
function projectFreshness(payload, now) {
  const data=structuredClone(payload);
  const monitor=data.monitor_freshness;
  const expired=!monitor?.expires_at || !Number.isFinite(Date.parse(monitor.expires_at)) || now>Date.parse(monitor.expires_at);
  if(expired){
    data.monitor_freshness={...monitor,status:monitor?.checked_at?'STALE':'UNKNOWN'};
    data.monitor_errors=[...(data.monitor_errors||[]),'Live verification expired; displayed run outcomes are historical.'];
  }
  for(const row of [...(data.engines||[]),...(data.trace_overview?.matrix||[])]){
    const r=row.readiness;
    if(!r||r.status==='NOT_CONFIGURED')continue;
    if(expired || !r.expires_at || now>Date.parse(r.expires_at)){
      r.status=r.checked_at?'STALE':'UNKNOWN';
      r.reason=expired?'Monitor updates stopped or collection expired.':'This capability check expired.';
      r.next_action='Check dsmonitor collection and automatic probe completion.';
      row.status=r.status;
      if('overall_status' in row)row.overall_status=r.status;
      if('connectivity_status' in row)row.connectivity_status='UNKNOWN';
      if('read_status' in row)row.read_status='UNKNOWN';
      if(expired&&'availability' in row)row.availability='UNKNOWN';
    }
  }
  if(data.trace_overview){
    data.trace_overview.health_summary={};
    for(const cell of data.trace_overview.matrix||[]){
      const counts=data.trace_overview.health_summary;counts[cell.status]=(counts[cell.status]||0)+1;
    }
  }
  if(expired){
    if(data.trace_overview?.summary)for(const k of ['running','waiting','stalled'])data.trace_overview.summary[k]=null;
    for(const k of ['engines_online','engines_degraded','active_processes','waiting_for_approval'])if(data.summary)data.summary[k]=null;
  }
  return data;
}
if(typeof module!=='undefined')module.exports={projectFreshness};

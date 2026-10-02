async function refreshDiagnostics(){
  const target=document.getElementById('diagnostic-reports');
  try {
    const response=await fetch('/api/diagnostics');
    if(!response.ok)throw new Error();
    const reports=await response.json();
    target.innerHTML=reports.length?reports.map(r=>`<article class="card"><h3>${esc(r.topic)} · ${badge(r.status)}</h3><p>Organization: ${esc(r.organization_id)}<br>Shared run: ${esc(r.workflow_run_id)}<br>Started: ${esc(r.started_at)} · Finished: ${esc(r.completed_at||'Still running or interrupted')}</p><p>${r.gaps?.length??0} observed gaps. A completed evaluation can deliberately reject all candidates.</p><div class="table-wrap"><table><thead><tr><th>Handoff / check</th><th>Status</th><th>Owner</th><th>Evidence</th><th>Next action</th></tr></thead><tbody>${(r.checks||[]).map(c=>`<tr><td>${esc(c.stage)}</td><td>${badge(c.status)}</td><td>${esc(c.owner)}</td><td>${esc(c.evidence)}</td><td>${esc(c.next_action)}</td></tr>`).join('')}</tbody></table></div></article>`).join(''):empty('No diagnostic cycles recorded. Run the command above to collect fresh evidence.');
  } catch(error){target.textContent='Diagnostic reports unavailable. Reload to retry.';}
}
document.getElementById('refresh-diagnostics').addEventListener('click',refreshDiagnostics);
document.addEventListener('click',event=>{if(event.target.closest('[data-tab="diagnostics"]'))refreshDiagnostics();});
refreshDiagnostics();

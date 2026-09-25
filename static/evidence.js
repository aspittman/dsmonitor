'use strict';
function evidenceOf(row){
  if(row.evidence_source)return row.evidence_source;
  if(row.source==='dsorchestrator')return {kind:'workflow',label:'Orchestrator workflow',location:'workflow_runs + stage_runs',meaning:'Recorded coordinator state; CRM references are verified separately.'};
  if(row.source==='crm')return {kind:'crm_record',label:(row.source_run_id||row.process_id||'').startsWith('crm-report:')?'Stored research report':'CRM recommendation records',location:'CRM API read-back',meaning:'A stored record was observed. This is not proof of a complete workflow or a downstream read.'};
  return {kind:'engine_log',label:row.source==='decision_log'?'Decision Engine log':'Source trace events',location:row.source==='decision_log'?'Configured decision log':'Configured source events',meaning:'Source evidence only; CRM persistence requires a separately verified record.'};
}
function evidenceStatus(row){
  const fragment=['crm','decision_log'].includes(row.source);
  return fragment&&row.status==='UNKNOWN'?'WORKFLOW NOT TRACKED':row.status;
}
function evidenceBlock(row){
  const source=evidenceOf(row);
  return `<div class="card evidence-explanation"><strong>${esc(source.label)}</strong><p>${esc(source.meaning)}</p><p class="muted">Read from: ${esc(source.location)}. Missing source timestamps are shown as not recorded; monitor observation time is not execution time.</p>${row.source==='crm'?'<button class="link" data-shared-engine="">Inspect CRM / Supabase evidence →</button>':''}</div>`;
}
function renderSharedState(){
  const data=state?.shared_state;
  if(!data?.engines){$('shared-content').innerHTML=empty('CRM evidence summary is not available from this monitor process yet.');return;}
  select('shared-engine','All engine owners',data.engines.map(e=>e.engine_id),engineName);
  select('shared-org','All monitored organizations',data.records.map(r=>r.organization_id),organizationName);
  const engine=$('shared-engine').value,org=$('shared-org').value;
  const rows=data.records.filter(r=>(!engine||r.owner_engine===engine)&&(!org||r.organization_id===org));
  const links=data.links.filter(r=>(!engine||r.reader_engine===engine)&&(!org||r.organization_id===org));
  $('shared-content').innerHTML=`<p class="muted">${esc(data.organizations_loaded)} of ${esc(data.organizations_configured)} configured organizations loaded. Oldest read-back: ${esc(time(data.observed_at))}. Counts describe stored records in the loaded context, not API calls or work today.</p>${data.organizations_loaded<data.organizations_configured?'<div class="alert">Some organization contexts are unavailable. Counts cover only the contexts that loaded.</div>':''}<div class="engine-grid">${data.engines.map(e=>`<button class="card" data-shared-engine="${esc(e.engine_id)}"><h3>${esc(engineName(e.engine_id))}</h3><p>${esc(e.stored_records??'Not verified')} stored records · ${esc(e.linked_inputs??'Not verified')} linked inputs</p><small>Contract owner of ${esc(e.tables.join(', '))}</small></button>`).join('')}</div><p class="muted">dsorchestrator: ${esc(data.workflow_records)} workflow records observed through ${esc(data.workflow_storage)}. A local workflow record is not proof it was persisted to Supabase.</p><h2>Stored records read back from CRM</h2><p class="muted">Engine ownership follows the architecture contract; this is not an authenticated caller audit. Select a record to inspect its source and references.</p>${rows.length?`<div class="table-wrap"><table><thead><tr><th>Record / table</th><th>Contract owner</th><th>Service / organization</th><th>Record status</th><th>Created in CRM</th></tr></thead><tbody>${rows.map(r=>`<tr><td><button class="link" data-shared-record="${esc(r.table+':'+r.id)}" data-record-org="${esc(r.organization_id)}">${esc(r.concept)}</button><small>${esc(r.table)} · ${esc(r.id)}</small></td><td>${esc(engineName(r.owner_engine))}</td><td>${esc(r.service_id||'Service not recorded')}<small>${esc(organizationName(r.organization_id))}</small></td><td>${esc(r.status||'Not recorded')}</td><td>${esc(r.created_at?time(r.created_at):'Timestamp not recorded')}</td></tr>`).join('')}</tbody></table></div>`:empty('No verified stored records in this selection. Check CRM access and organization scope; this does not prove no writes occurred.')}<h2>Explicit handoffs and evidence links</h2><p class="muted">A downstream record cites an upstream record. This establishes a stored relationship, not the time or success of an HTTP/SQL read.</p>${links.length?links.map(l=>`<div class="feed"><div><strong>${esc(l.description)}</strong><p>${esc(l.from_table)} → ${esc(l.to_table)}</p><small>${esc(organizationName(l.organization_id))} · ${esc(l.from_id)} → ${esc(l.to_id)}</small></div></div>`).join(''):empty('No explicit cross-record references were verified in this selection. An isolated report does not prove Decision Engine received it.')}${data.limited?'<p class="muted">Showing up to 200 recent records and 200 links. Summary counts include the full loaded contexts.</p>':''}<h2>What the monitor can and cannot see</h2><p>${esc(data.limitation)}</p><p class="muted">Monitor reads: ${esc(data.read_api_paths.join(' · '))}. CRM serves the stored Supabase records. The separate Supabase health probe checks connectivity, not engine traffic.</p>`;
}
function showSharedRecord(key,org){
  const data=state?.shared_state;
  const row=data?.records.find(r=>r.table+':'+r.id===key&&r.organization_id===org);
  if(!row)return;
  const links=data.links.filter(l=>l.organization_id===org&&(l.from_table+':'+l.from_id===key||l.to_table+':'+l.to_id===key));
  show(row.concept,`<p>${esc(row.meaning)}</p>${detailFields([['Source','CRM API read-back of Supabase'],['Table',row.table],['Record ID',row.id],['Contract owner',engineName(row.owner_engine)],['Organization',organizationName(org)],['Service',row.service_id||'Not recorded'],['Workflow ID',row.workflow_run_id||'Not recorded on this record'],['Record status',row.status||'Not recorded'],['Created in CRM',row.created_at?time(row.created_at):'Not recorded'],['Completed',row.completed_at?time(row.completed_at):'Not recorded'],['Monitor read-back',time(row.observed_at)]])}<h2>Verified references</h2>${links.map(l=>`<p>${esc(l.description)}: ${esc(l.from_table)} / ${esc(l.from_id)} → ${esc(l.to_table)} / ${esc(l.to_id)}</p>`).join('')||empty('No explicit references were verified for this record.')}<p class="muted">The monitor displays record identity and lineage, not the original request body or customer payload.</p>`);
}
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.hasAttribute('data-shared-engine')){if($('detail').open)$('detail').close();tab('shared-state');$('shared-engine').value=button.dataset.sharedEngine;renderSharedState();}
  if(button.dataset.sharedRecord)showSharedRecord(button.dataset.sharedRecord,button.dataset.recordOrg);
});
$('shared-filters').addEventListener('change',renderSharedState);

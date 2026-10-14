(() => {
 'use strict';
 const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const labels={pending:'Da prendere in carico',in_progress:'In corso',completed:'Completata',not_required:'Non necessario',cancelled:'Annullata'};
 const eventLabels={created:'Attività creata',claim:'Presa in carico',release:'Rilasciata',complete:'Completata',not_required:'Lotti non necessari',reopen:'Riaperta',cancel:'Annullata',photo_added:'Foto aggiunta',photo_removed:'Foto rimossa'};
 const status=row=>`<span class="activity-status ${row.status}">${esc(labels[row.status]||row.status)}</span>`;
 const date=value=>value?new Date(value.length===10?value+'T12:00:00':value+'Z').toLocaleString('it-IT',{dateStyle:'short',...(value.length===10?{}:{timeStyle:'short'})}):'';
 let page=1,generation=0,selected=null,activity=null,detailGeneration=0,busy=false,routing=null,routingBusy=false,sourceCard=null,arrivalKey=null,arrivalBusy=false,searchTimer;
 const params=new URLSearchParams(location.search),isManager=$('activityPage').dataset.manager==='1';
 async function api(url,options={}) {
  const multipart=options.body instanceof FormData;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),multipart?60000:30000);
  try {
   const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options,signal:controller.signal,headers:{Accept:'application/json','X-Requested-With':'XMLHttpRequest',...(multipart?{}:{'Content-Type':'application/json'}),...(options.headers||{})}});
   const result=await response.json().catch(()=>({}));
   if(response.redirected)throw Error('Sessione scaduta. Accedi di nuovo.');
   if(!response.ok||result.ok!==true)throw Error(result.error||'Attività non disponibili. Riprova.');return result;
  } catch(error){if(error.name==='AbortError')throw Error('La richiesta ha impiegato troppo tempo. Aggiorna e riprova.');throw error;}
  finally{clearTimeout(timer);}
 }
 function groupRows(rows) {
  const groups=new Map();rows.forEach(row=>{const key=row.source?'arrival-'+row.source.id:'activity-'+row.id;if(!groups.has(key))groups.set(key,{source:row.source,rows:[]});groups.get(key).rows.push(row);});
  return [...groups.values()].map(group=>`<article class="activity-group"><h2>${esc(group.source?.label||'Attività')}</h2>${group.source?`<p>${esc(group.source.reference)} · Ricevuta ${esc(date(group.source.received_on))}${group.source.partial?' · Consegna parziale':''}</p>${group.source.note?`<p>${esc(group.source.note)}</p>`:''}`:''}${group.rows.map(row=>`<div class="activity-row"><div><strong>${esc(row.title)}</strong><br>${status(row)}${row.owner?`<div>In carico a ${esc(row.owner)}</div>`:''}${row.description?`<p class="activity-description">${esc(row.description)}</p>`:''}<small>${esc([...row.roles,...(row.users||[]).map(user=>user.name)].join(', '))}</small></div><button type="button" class="btn btn-info" data-open-activity="${row.id}">Apri attività</button></div>`).join('')}</article>`).join('');
 }
 async function load(silent=false) {
  const request=++generation;if(!silent)$('activityFeedback').textContent='Caricamento…';
  try {
   const query=new URLSearchParams({status:$('activityStatus').value,page:String(page),q:$('activitySearch').value});if(params.get('arrival'))query.set('arrival',params.get('arrival'));
   const result=await api('/activities/api?'+query);if(request!==generation)return;
   const c=result.counts,counters=`<span>Da fare: ${c.pending||0}</span><span>In corso: ${c.in_progress||0}</span><span>Completate: ${(c.completed||0)+(c.not_required||0)}</span>`;
   if($('activityCounts').innerHTML!==counters)$('activityCounts').innerHTML=counters;
   const markup=groupRows(result.rows)||'<div class="activity-group">Nessuna attività per questo filtro.</div>';
   if($('activityList').innerHTML!==markup){
    const focus=$('activityList').contains(document.activeElement)?document.activeElement.dataset.openActivity:null;
    $('activityList').innerHTML=markup;
    $('activityList').querySelectorAll('[data-open-activity]').forEach(button=>button.onclick=()=>openDetail(Number(button.dataset.openActivity)));
    if(focus)$('activityList').querySelector(`[data-open-activity="${focus}"]`)?.focus({preventScroll:true});
   }
   $('activityPrevious').disabled=page<=1;$('activityNext').disabled=page>=result.pages;$('activityPageLabel').textContent=`Pagina ${page} di ${Math.max(1,result.pages)} · ${result.total} attività`;$('activityFeedback').textContent='';
  } catch(error){if(request===generation)$('activityFeedback').textContent=error.message;}
 }
 function renderDetail(note='') {
  const row=activity,active=['pending','in_progress'].includes(row.status),can=active&&row.can_act;
  const actions=[];
  if(can){if(row.status==='pending')actions.push(['claim','Prendi in carico']);else actions.push(['release','Rilascia']);actions.push(['complete',row.kind==='lots'?'Conferma lotti inviati':row.kind==='check_goods'?'Merce controllata':row.kind==='manual'?'Completa attività':'Prodotti sistemati']);if(row.kind==='lots')actions.push(['not_required','Non necessario']);}
  if(row.can_manage)actions.push(active?['cancel','Annulla attività']:['reopen','Riapri attività']);
  const source=row.source;
  $('activityModalTitle').textContent=row.title;
  $('activityDetail').innerHTML=`${source?`<h6>${esc(source.label)}</h6><p>${esc(source.reference)} · ${esc(date(source.received_on))}${source.partial?' · Consegna parziale':''}</p>${source.note?`<p>${esc(source.note)}</p>`:''}${row.can_manage&&source.card_id?`<a href="/supplier-orders/board?card_id=${source.card_id}&archived=1">Apri scheda fornitore</a>`:''}`:''}${row.description?`<p class="activity-description">${esc(row.description)}</p>`:''}<p>Destinatari: ${esc([...row.roles,...(row.users||[]).map(user=>user.name)].join(', '))}</p><p>${status(row)}${row.owner?` · ${esc(row.owner)}`:''}</p>${active&&!row.can_act?'<p>Un’altra persona sta seguendo questa attività.</p>':''}${actions.length?`<div class="activity-detail-note"><label class="form-label" for="activityNote">Nota / motivazione</label><textarea id="activityNote" class="form-control" maxlength="2000" rows="3">${esc(note)}</textarea><small>La motivazione è obbligatoria per Non necessario, riapertura e annullamento.</small></div><div class="activity-actions">${actions.map(([action,label])=>`<button type="button" class="btn ${action==='cancel'?'btn-outline-danger':'btn-info'}" data-activity-action="${action}">${esc(label)}</button>`).join('')}</div>`:''}
   ${row.kind==='lots'?`<h6 class="mt-3">Foto dei lotti</h6><div class="activity-photos">${row.photos.map(photo=>`<div class="activity-photo"><a href="${esc(photo.url)}" target="_blank" rel="noopener"><img src="${esc(photo.url)}" alt="${esc(photo.label)}" loading="lazy"></a><p>${esc(photo.label)}${photo.cycle!==row.cycle?' · lavorazione precedente':''}</p>${can&&photo.cycle===row.cycle?`<button type="button" class="btn btn-outline-danger" data-remove-photo="${photo.id}">Rimuovi foto</button>`:''}</div>`).join('')||'<p>Nessuna foto allegata.</p>'}</div>${can?'<div class="activity-photo-form"><label class="form-label" for="activityPhotoLabel">Prodotto fotografato</label><input id="activityPhotoLabel" class="form-control" maxlength="200" placeholder="Prodotto, annata o riferimento"><label class="form-label" for="activityPhotoFile">Foto lotto / scadenza</label><input id="activityPhotoFile" type="file" class="form-control" accept="image/jpeg,image/png,image/webp"><small>JPEG, PNG o WebP, massimo 8 MB. Puoi allegare fino a 20 foto.</small><button id="activityPhotoUpload" class="btn btn-info" type="button">Allega foto</button></div>':''}`:''}
   <h6 class="mt-3">Storico</h6><ol class="activity-history">${row.events.map(event=>`<li><strong>${esc(eventLabels[event.action]||event.action)}</strong> · ${esc(event.actor)}<br><small>${esc(date(event.created_at))}</small>${event.note?`<br>${esc(event.note)}`:''}</li>`).join('')}</ol>`;
  setDetailBusy(busy);
 }
 function setDetailBusy(value) {busy=value;$('activityModal').querySelectorAll('button,input,textarea').forEach(element=>element.disabled=value);}
 async function readDetail() {
  const id=selected,request=++detailGeneration;if(!id)return;
  $('activityError').textContent='';$('activityDetail').textContent='Caricamento attività…';
  try {const result=await api('/activities/api/'+id);if(request!==detailGeneration||selected!==id)return;activity=result.activity;renderDetail();}
  catch(error){if(request===detailGeneration)$('activityError').textContent=error.message;}
 }
 function openDetail(id) {selected=id;activity=null;bootstrap.Modal.getOrCreateInstance($('activityModal')).show();readDetail();}
 async function runAction(action) {
  if(busy||!activity)return;const note=$('activityNote')?.value||'';
  if(['cancel','reopen','not_required'].includes(action)&&!note.trim()){$('activityError').textContent='Inserisci la motivazione.';return;}
  if(action==='cancel'&&!confirm('Annullare questa attività? La motivazione resterà nello storico.'))return;
  setDetailBusy(true);$('activityError').textContent='';
  try {const result=await api(`/activities/api/${activity.id}/actions`,{method:'POST',body:JSON.stringify({action,note,revision:activity.revision})});activity=result.activity;renderDetail();await load();}
  catch(error){$('activityError').textContent=error.message;}
  finally{setDetailBusy(false);}
 }
 async function upload() {
  if(busy||!activity)return;const file=$('activityPhotoFile').files[0],label=$('activityPhotoLabel').value.trim(),note=$('activityNote')?.value||'';
  if(!file||!label){$('activityError').textContent='Indica il prodotto e scegli una foto.';return;}
  if(file.size>8*1024*1024){$('activityError').textContent='La foto supera 8 MB.';return;}
  const body=new FormData();body.set('photo',file);body.set('label',label);body.set('revision',String(activity.revision));setDetailBusy(true);$('activityError').textContent='';
  try {const result=await api(`/activities/api/${activity.id}/photos`,{method:'POST',body});activity=result.activity;renderDetail(note);await load();}
  catch(error){$('activityError').textContent=error.message;}
  finally{setDetailBusy(false);}
 }
 async function removePhoto(id) {
  if(busy||!confirm('Rimuovere questa foto dalla lavorazione corrente?'))return;
  const note=$('activityNote')?.value||'';setDetailBusy(true);$('activityError').textContent='';
  try {const result=await api('/activities/api/photos/'+id,{method:'DELETE',body:JSON.stringify({revision:activity.revision})});activity=result.activity;renderDetail(note);}
  catch(error){$('activityError').textContent=error.message;}
  finally{setDetailBusy(false);}
 }
 function routingControls(value){routingBusy=value;$('activityRoutingModal').querySelectorAll('button,input').forEach(element=>element.disabled=value);}
 async function readRouting() {
  routingControls(true);$('activityRoutingError').textContent='';
  try {routing=await api('/activities/api/routing');$('activityRoutingFields').innerHTML=Object.entries(routing.kinds).map(([kind,title])=>`<fieldset class="activity-routing-step"><legend>${esc(title)}</legend>${routing.roles.map(role=>`<label class="activity-checkbox"><input type="checkbox" data-routing-kind="${esc(kind)}" value="${role.id}" ${routing.rules[kind]?.includes(role.id)?'checked':''}> ${esc(role.name)}</label>`).join('')}</fieldset>`).join('');}
  catch(error){$('activityRoutingError').textContent=error.message;}
  finally{routingControls(false);}
 }
 async function saveRouting() {
  if(routingBusy||!routing)return;const rules=Object.fromEntries(Object.keys(routing.kinds).map(kind=>[kind,[...$('activityRoutingFields').querySelectorAll(`[data-routing-kind="${kind}"]:checked`)].map(input=>Number(input.value))]));
  routingControls(true);$('activityRoutingError').textContent='';
  try {await api('/activities/api/routing',{method:'PUT',body:JSON.stringify({revision:routing.revision,rules})});routingControls(false);bootstrap.Modal.getInstance($('activityRoutingModal')).hide();}
  catch(error){$('activityRoutingError').textContent=error.message;}
  finally{routingControls(false);}
 }
 async function openArrival(cardId) {
  sourceCard=null;arrivalKey=crypto.randomUUID?crypto.randomUUID():[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');
  const d=new Date();$('activityArrivalDate').value=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');$('activityArrivalNote').value='';$('activityArrivalPartial').checked=false;$('activityArrivalError').textContent='';$('activityArrivalSource').textContent='Caricamento scheda…';$('activityArrivalSave').disabled=true;
  bootstrap.Modal.getOrCreateInstance($('activityArrivalModal')).show();
  const key=arrivalKey;
  try {const result=await api('/activities/api/source-card/'+cardId);if(key!==arrivalKey)return;sourceCard=result.card;$('activityArrivalSource').textContent=sourceCard.title;$('activityArrivalSave').disabled=false;}
  catch(error){if(key===arrivalKey)$('activityArrivalError').textContent=error.message;}
 }
 function arrivalControls(value){arrivalBusy=value;$('activityArrivalModal').querySelectorAll('button,input,textarea').forEach(element=>element.disabled=value);}
 async function saveArrival() {
  if(arrivalBusy||!sourceCard)return;arrivalControls(true);$('activityArrivalError').textContent='';
  const payload={card_id:sourceCard.id,revision:sourceCard.revision,event_key:arrivalKey,received_on:$('activityArrivalDate').value,partial:$('activityArrivalPartial').checked,note:$('activityArrivalNote').value};
  try {const result=await api('/activities/api/supplier-arrivals',{method:'POST',body:JSON.stringify(payload)});arrivalBusy=false;bootstrap.Modal.getInstance($('activityArrivalModal')).hide();params.delete('arrival_card');params.set('arrival',result.arrival_id);history.replaceState({},'',location.pathname+'?'+params);page=1;await load();}
  catch(error){$('activityArrivalError').textContent=error.message;}
  finally{arrivalControls(false);}
 }
 document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.activity-modal').forEach(modal=>{
   document.body.appendChild(modal);modal.addEventListener('show.bs.modal',()=>document.body.classList.add('activity-modal-open'));
   modal.addEventListener('hidden.bs.modal',()=>document.body.classList.remove('activity-modal-open'));
  });
  $('activityModal').addEventListener('shown.bs.modal',()=>{
   setDetailBusy(busy);$('activityDetailRefresh').onclick=readDetail;
   $('activityDetail').onclick=event=>{const action=event.target.closest('[data-activity-action]'),remove=event.target.closest('[data-remove-photo]');if(action)runAction(action.dataset.activityAction);else if(remove)removePhoto(Number(remove.dataset.removePhoto));else if(event.target.closest('#activityPhotoUpload'))upload();};
  });
  $('activityModal').addEventListener('hide.bs.modal',event=>{if(busy)event.preventDefault();});
  $('activityModal').addEventListener('hidden.bs.modal',()=>{selected=null;activity=null;detailGeneration++;$('activityDetail').onclick=null;$('activityDetailRefresh').onclick=null;$('activityError').textContent='';});
  if(isManager){
   window.ActivityCreate?.init({api,onCreated:async()=>{params.delete('arrival');page=1;$('activityStatus').value='active';$('activitySearch').value='';history.replaceState({},'',location.pathname);await load();}});
   $('activityRouting').onclick=()=>{bootstrap.Modal.getOrCreateInstance($('activityRoutingModal')).show();readRouting();};
   $('activityRoutingModal').addEventListener('shown.bs.modal',()=>{routingControls(routingBusy);$('activityRoutingSave').onclick=saveRouting;$('activityRoutingReload').onclick=readRouting;});
   $('activityRoutingModal').addEventListener('hide.bs.modal',event=>{if(routingBusy)event.preventDefault();});
   $('activityRoutingModal').addEventListener('hidden.bs.modal',()=>{routing=null;$('activityRoutingSave').onclick=null;$('activityRoutingReload').onclick=null;});
   $('activityArrivalModal').addEventListener('shown.bs.modal',()=>{$('activityArrivalSave').disabled=!sourceCard||arrivalBusy;$('activityArrivalSave').onclick=saveArrival;});
   $('activityArrivalModal').addEventListener('hide.bs.modal',event=>{if(arrivalBusy)event.preventDefault();});
   $('activityArrivalModal').addEventListener('hidden.bs.modal',()=>{sourceCard=null;arrivalKey=null;$('activityArrivalSave').onclick=null;});
   if(params.get('arrival_card'))openArrival(Number(params.get('arrival_card')));
  }
  const reset=()=>{page=1;load();};$('activityRefresh').onclick=()=>{params.delete('arrival');history.replaceState({},'',location.pathname);reset();};$('activityStatus').onchange=reset;
  $('activitySearch').oninput=()=>{clearTimeout(searchTimer);generation++;searchTimer=setTimeout(reset,250);};$('activityPrevious').onclick=()=>{page--;load();};$('activityNext').onclick=()=>{page++;load();};
  load();const timer=setInterval(()=>{if(!document.hidden&&!document.querySelector('.activity-modal.show'))load(true);},30000);window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  if(params.get('activity')&&!(isManager&&params.get('arrival_card')))openDetail(Number(params.get('activity')));
 });
})();

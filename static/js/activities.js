(() => {
 'use strict';
 const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const labels={pending:'Da prendere in carico',in_progress:'In corso',completed:'Completata',not_required:'Non necessario',cancelled:'Annullata'};
 const eventLabels={updated:'Attività modificata',child_created:'Sottoattività creata',linked:'Collegamento principale',created:'Attività creata',claim:'Presa in carico',release:'Rilasciata',complete:'Completata',not_required:'Lotti non necessari',reopen:'Riaperta',cancel:'Annullata',photo_added:'Foto aggiunta',photo_removed:'Foto rimossa',files_added:'Allegati aggiunti',file_removed:'Allegato rimosso'};
 const status=row=>`<span class="activity-status ${row.status}">${esc(labels[row.status]||row.status)}</span>`;
 const date=value=>value?new Date(value.length===10?value+'T12:00:00':value+'Z').toLocaleString('it-IT',{dateStyle:'short',...(value.length===10?{}:{timeStyle:'short'})}):'';
 let page=1,generation=0,selected=null,activity=null,detailGeneration=0,busy=false,routing=null,routingBusy=false,sourceCard=null,arrivalKey=null,arrivalBusy=false,searchTimer,arrivalDirectory={roles:[],users:[]};
 const arrivalSelectedUsers=new Map(),arrivalSearchRequests=new Map();
 const params=new URLSearchParams(location.search),isManager=$('activityPage').dataset.manager==='1';
 async function api(url,options={}) {
  const multipart=options.body instanceof FormData;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),multipart?60000:30000);
  try {
   const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options,signal:controller.signal,headers:{Accept:'application/json','X-Requested-With':'XMLHttpRequest',...(multipart?{}:{'Content-Type':'application/json'}),...(options.headers||{})}});
   const result=await response.json().catch(()=>({}));
   if(response.redirected)throw Error('Sessione scaduta. Accedi di nuovo.');
   if(!response.ok||result.ok!==true)throw Error(result.error||`Errore ${response.status} durante il caricamento delle attività. Aggiorna e riprova.`);return result;
  } catch(error){if(error.name==='AbortError')throw Error('La richiesta ha impiegato troppo tempo. Aggiorna e riprova.');throw error;}
  finally{clearTimeout(timer);}
 }
 function groupRows(rows) {
  const ids=new Set(rows.map(r=>r.id)),children=new Map(),roots=[];
  rows.forEach(row=>{if(row.parent_id&&ids.has(row.parent_id)){if(!children.has(row.parent_id))children.set(row.parent_id,[]);children.get(row.parent_id).push(row);}else roots.push(row);});
  const done=row=>['completed','not_required'].includes(row.status);
  function branch(row){
   const sub=(children.get(row.id)||[]).sort((a,b)=>Number(done(b))-Number(done(a))||(a.completed_at||'').localeCompare(b.completed_at||'')||a.id-b.id);
   return `<li class="activity-tree-node ${done(row)&&row.parent_id?'is-pinned':''}"><div class="activity-row"><div>${ActivityTree.title(row,(done(row)&&row.parent_id?'📌 ':'')+esc(row.title),sub.length)}<br>${status(row)}${row.owner?`<div>In carico a ${esc(row.owner)}</div>`:''}${row.description?`<p class="activity-description">${esc(row.description)}</p>`:''}<small>${esc(ActivityRecipients(row))}</small></div><button type="button" class="btn btn-info" data-open-activity="${row.id}">Apri attività</button></div>${sub.length?'<ul class="activity-tree"'+ActivityTree.hidden(row.id)+'>'+sub.map(branch).join('')+'</ul>':''}</li>`;
  }
  return roots.map(row=>'<article class="activity-group">'+(row.source?`<h2>${esc(row.source.label)}</h2><p>${esc(row.source.reference)} · Ricevuta ${esc(date(row.source.received_on))}</p>`:'')+'<ul class="activity-tree">'+branch(row)+'</ul></article>').join('');
 }
 async function load(silent=false) {
  const request=++generation;if(!silent)$('activityFeedback').textContent='Caricamento…';
  try {
   const query=new URLSearchParams({status:$('activityStatus').value,page:String(page),q:$('activitySearch').value});if(params.get('arrival'))query.set('arrival',params.get('arrival'));
   const result=await api('/activities/api?'+query);if(request!==generation)return;
   await loadResults();if(request!==generation)return;
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
  const structure=`<div class="activity-actions mb-3">${row.can_edit?'<button class="btn btn-info" type="button" data-edit-activity>Modifica attività</button>':''}${row.can_create_child?'<button class="btn btn-info" type="button" data-new-child>Crea sottoattività</button>':''}${row.parent_visible?`<button class="btn btn-outline-secondary" type="button" data-related-activity="${row.parent_id}">Apri attività principale</button>`:''}</div>${row.blocked_children?`<p class="activity-error">In attesa degli esiti di ${row.blocked_children} sottoattività. Il completamento è bloccato.</p>`:''}${row.children?.length?'<h6>Sottoattività</h6><ul>'+[...row.children].sort((a,b)=>Number(['completed','not_required'].includes(b.status))-Number(['completed','not_required'].includes(a.status))).map(child=>`<li>${['completed','not_required'].includes(child.status)?'📌 ':''}<button class="btn btn-link" data-related-activity="${child.id}" type="button">${esc(child.title)}</button> · ${esc(labels[child.status])}</li>`).join('')+'</ul>':''}`;
  $('activityModalTitle').textContent=row.title;
  $('activityDetail').innerHTML=`${structure}${source?`<h6>${esc(source.label)}</h6><p>${esc(source.reference)} · ${esc(date(source.received_on))}${source.partial?' · Consegna parziale':''}</p>${source.note?`<p>${esc(source.note)}</p>`:''}${row.can_manage&&source.card_id?`<a href="/supplier-orders/board?card_id=${source.card_id}&archived=1">Apri scheda fornitore</a>`:''}`:''}${row.description?`<p class="activity-description">${esc(row.description)}</p>`:''}<p>Incaricati: ${esc(ActivityRecipients(row))}</p><p>Destinatari notifiche / esito: ${esc(ActivityRecipients(row.result_recipients||{})||'Non configurati')}</p><p>${status(row)}${row.owner?` · ${esc(row.owner)}`:''}</p>${active&&!row.can_act?'<p>Un’altra persona sta seguendo questa attività.</p>':''}${actions.length?`<div class="activity-detail-note"><label class="form-label" for="activityNote">Nota / motivazione</label><textarea id="activityNote" class="form-control" maxlength="2000" rows="3">${esc(note)}</textarea><small>La motivazione è obbligatoria per Non necessario, riapertura e annullamento.</small></div><div class="activity-actions">${actions.map(([action,label])=>`<button type="button" class="btn ${action==='cancel'?'btn-outline-danger':'btn-info'}" data-activity-action="${action}" ${['complete','not_required'].includes(action)&&row.blocked_children?'data-dependency-blocked="1"':''}>${esc(label)}</button>`).join('')}</div>`:''}
   ${row.kind==='lots'?`<h6 class="mt-3">Foto dei lotti</h6><div class="activity-photos">${row.photos.map(photo=>`<div class="activity-photo"><a href="${esc(photo.url)}" target="_blank" rel="noopener"><img src="${esc(photo.url)}" alt="${esc(photo.label)}" loading="lazy"></a><p>${esc(photo.label)}${photo.cycle!==row.cycle?' · lavorazione precedente':''}</p>${can&&photo.cycle===row.cycle?`<button type="button" class="btn btn-outline-danger" data-remove-photo="${photo.id}">Rimuovi foto</button>`:''}</div>`).join('')||'<p>Nessuna foto allegata.</p>'}</div>${can?'<div class="activity-photo-form"><label class="form-label" for="activityPhotoLabel">Prodotto fotografato *</label><input id="activityPhotoLabel" class="form-control" maxlength="200" placeholder="Prodotto, annata o riferimento"><label class="form-label" for="activityPhotoFile">Foto lotto / scadenza</label><input id="activityPhotoFile" type="file" class="visually-hidden" accept="image/jpeg,image/png,image/webp" capture="environment"><button id="activityPhotoCapture" class="btn btn-info" type="button">Scatta foto</button><span id="activityPhotoName" class="small ms-2">Nessuna foto selezionata</span><small class="d-block mt-1">La foto deve essere etichettata con il prodotto. JPEG, PNG o WebP, massimo 8 MB; fino a 20 foto.</small><button id="activityPhotoUpload" class="btn btn-info mt-2" type="button">Allega foto</button></div>':''}`:''}
   <h6 class="mt-3">${row.kind==='lots'?'Documenti allegati':'File e foto allegati'}</h6><ul>${(row.attachments||[]).map(file=>`<li><a href="${esc(file.url)}">${esc(file.filename)}</a> · ${file.purpose==='instructions'?'Istruzioni':'Esito / lavorazione'}${file.cycle!==row.cycle?' · lavorazione precedente':''}${can&&file.purpose==='result'&&file.cycle===row.cycle?` <button type="button" class="btn btn-sm btn-outline-danger" data-remove-file="${file.id}">Rimuovi</button>`:''}</li>`).join('')||'<li>Nessun allegato.</li>'}</ul>${can?`<label class="form-label" for="activityFiles">${row.kind==='lots'?'Allega documenti (le foto dei lotti si aggiungono nella sezione sopra)':'Allega file / foto alla lavorazione o all’esito'}</label><input id="activityFiles" class="form-control" type="file" multiple accept="${row.kind==='lots'?'.pdf,.doc,.docx,.xls,.xlsx':'.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp'}"><small>10 file, 10 MB ciascuno, 50 MB totali.</small><button id="activityFilesUpload" class="btn btn-info mt-2" type="button">Carica allegati</button>`:''}
   <h6 class="mt-3">Storico</h6><ol class="activity-history">${row.events.map(event=>`<li><strong>${esc(eventLabels[event.action]||event.action)}</strong> · ${esc(event.actor)}<br><small>${esc(date(event.created_at))}</small>${event.note?`<br>${esc(event.note)}`:''}</li>`).join('')}</ol>`;
  setDetailBusy(busy);
 }
 function setDetailBusy(value) {busy=value;$('activityModal').querySelectorAll('button,input,textarea').forEach(element=>element.disabled=value||element.dataset.dependencyBlocked==='1');}
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
 $('activityDetail').addEventListener('change',event=>{if(event.target.id==='activityPhotoFile')$('activityPhotoName').textContent=event.target.files[0]?.name||'Nessuna foto selezionata';});
 $('activityDetail').addEventListener('click',event=>{if(event.target.closest('#activityPhotoCapture'))$('activityPhotoFile').click();});
 async function loadResults(){
  try{
   const data=await api('/activities/api/results');
   $('activityResults').innerHTML=data.rows.map(row=>`<p>${row.can_open===false?esc(row.title):`<button class="btn btn-link" type="button" data-result-open="${row.activity_id}">${esc(row.title)}</button>`} · ${esc((row.message||row.note||'').slice(0,500))}${(row.message||row.note||'').length>500?'…':''} <button class="btn btn-sm btn-outline-secondary" type="button" data-result-read="${row.id}">Segna letto</button></p>`).join('')||'<p>Nessuna nuova notifica.</p>';
   $('activityResults').onclick=async event=>{
    const open=event.target.closest('[data-result-open]'),read=event.target.closest('[data-result-read]');
    if(open)openDetail(Number(open.dataset.resultOpen));
    if(read){read.disabled=true;try{await api('/activities/api/results/'+read.dataset.resultRead+'/read',{method:'POST',body:'{}'});await loadResults();}catch(error){$('activityFeedback').textContent=error.message;read.disabled=false;}}
   };
  }catch(error){$('activityResults').textContent=error.message;}
 }
 async function uploadFiles(){
  if(busy||!activity)return;
  const body=new FormData(),note=$('activityNote')?.value||'';for(const file of $('activityFiles').files)body.append('files',file);
  body.set('revision',String(activity.revision));setDetailBusy(true);$('activityError').textContent='';
  try{const result=await api('/activities/api/'+activity.id+'/attachments',{method:'POST',body});activity=result.activity;renderDetail(note);}
  catch(error){$('activityError').textContent=error.message;}finally{setDetailBusy(false);}
 }
 async function removeFile(id){
  if(busy||!confirm('Rimuovere questo allegato?'))return;
  const note=$('activityNote')?.value||'';setDetailBusy(true);
  try{const result=await api('/activities/api/attachments/'+id,{method:'DELETE',body:JSON.stringify({revision:activity.revision})});activity=result.activity;renderDetail(note);}
  catch(error){$('activityError').textContent=error.message;}finally{setDetailBusy(false);}
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
 const arrivalKinds={check_goods:'Controllare la merce',lots:'Inviare i lotti',store_goods:'Sistemare i prodotti in magazzino'};
 function arrivalPicker(kind,audience,roleNames,defaultMinimum=null) {
  const key=`${kind}:${audience}`,name=audience==='assignees'?'Incaricati':'Destinatari dell’esito';
  const defaults=arrivalDirectory.roles.filter(role=>roleNames.includes(role.name.trim().toLocaleLowerCase('it-IT'))).map(role=>role.id);
  const weights=new Map();arrivalDirectory.roles.forEach(role=>{if(!weights.has(role.weight))weights.set(role.weight,[]);weights.get(role.weight).push(role.name);});
  const minimumOptions=[...weights].sort((a,b)=>a[0]-b[0]).map(([weight,names])=>`<option value="${weight}" ${weight===defaultMinimum?'selected':''}>${esc(names.join(', '))} e superiori</option>`).join('');
  return `<fieldset class="activity-arrival-picker" data-arrival-picker="${key}"><legend>${name}</legend><div class="activity-arrival-picker-roles">${arrivalDirectory.roles.map(role=>`<label class="activity-checkbox"><input type="checkbox" data-arrival-role="${role.id}" ${defaults.includes(role.id)?'checked':''}> ${esc(role.name)}</label>`).join('')}</div><label class="form-label" for="arrival-min-${kind}-${audience}">Oppure includi i ruoli con peso minimo</label><select id="arrival-min-${kind}-${audience}" class="form-select" data-arrival-minimum><option value="">Nessuna soglia minima</option>${minimumOptions}</select><label class="form-label mt-2" for="arrival-user-search-${kind}-${audience}">Aggiungi singoli utenti</label><input id="arrival-user-search-${kind}-${audience}" class="form-control" data-arrival-user-search type="search" placeholder="Cerca nome utente"><div class="activity-arrival-users" data-arrival-users></div><small data-arrival-users-hint>${arrivalDirectory.users.length} utenti operativi mostrati; cerca per restringere.</small></fieldset>`;
 }
 function renderArrivalUserList(kind,audience,users) {
  const key=`${kind}:${audience}`,picker=$(`[data-arrival-picker="${key}"]`);if(!picker)return;
  if(!arrivalSelectedUsers.has(key))arrivalSelectedUsers.set(key,new Map());
  const selectedUsers=arrivalSelectedUsers.get(key);
  picker.querySelector('[data-arrival-users]').innerHTML=users.map(user=>`<label class="activity-checkbox"><input type="checkbox" data-arrival-user="${user.id}" ${selectedUsers.has(user.id)?'checked':''}> ${esc(user.name)}</label>`).join('')||'<small>Nessun utente trovato.</small>';
 }
 function renderArrivalTasks() {
  const staffNames=['staff'],officeNames=['office','ufficio'];
  $('activityArrivalTasks').innerHTML=Object.entries(arrivalKinds).map(([kind,title])=>`<section class="activity-arrival-task" data-arrival-task="${kind}"><label class="activity-arrival-task-toggle"><input type="checkbox" data-arrival-enabled="${kind}" checked><strong>${esc(title)}</strong></label><details><summary>Configura incaricati e destinatari</summary><div class="activity-arrival-task-config">${arrivalPicker(kind,'assignees',staffNames)}${arrivalPicker(kind,'recipients',officeNames)}</div></details></section>`).join('');
  for(const [kind] of Object.entries(arrivalKinds))for(const audience of ['assignees','recipients'])renderArrivalUserList(kind,audience,arrivalDirectory.users);
 }
 async function loadArrivalUsers(input) {
  const picker=input.closest('[data-arrival-picker]'),[kind,audience]=picker.dataset.arrivalPicker.split(':');
  const key=picker.dataset.arrivalPicker,request=(arrivalSearchRequests.get(key)||0)+1;arrivalSearchRequests.set(key,request);
  picker.querySelector('[data-arrival-users-hint]').textContent='Ricerca utenti…';
  try {const data=await api('/activities/api/assignees?'+new URLSearchParams({q:input.value.trim()}));if(arrivalSearchRequests.get(key)!==request)return;const known=new Map(arrivalDirectory.users.map(user=>[user.id,user]));data.users.forEach(user=>known.set(user.id,user));arrivalDirectory.users=[...known.values()];renderArrivalUserList(kind,audience,data.users);picker.querySelector('[data-arrival-users-hint]').textContent=`${data.users.length} utenti trovati${data.total>data.users.length?' (restringi la ricerca)':''}.`;}
  catch(error){if(arrivalSearchRequests.get(key)===request)picker.querySelector('[data-arrival-users-hint]').textContent=error.message;}
 }
 async function openArrival(cardId) {
  sourceCard=null;arrivalKey=crypto.randomUUID?crypto.randomUUID():[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');
  const d=new Date();$('activityArrivalDate').value=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');$('activityArrivalNote').value='';$('activityArrivalPartial').checked=false;$('activityArrivalError').textContent='';$('activityArrivalSource').textContent='Caricamento scheda…';$('activityArrivalSave').disabled=true;
  bootstrap.Modal.getOrCreateInstance($('activityArrivalModal')).show();
  const key=arrivalKey;
  try {const [result,people]=await Promise.all([api('/activities/api/source-card/'+cardId),api('/activities/api/assignees')]);if(key!==arrivalKey)return;sourceCard=result.card;arrivalDirectory=people;arrivalSelectedUsers.clear();arrivalSearchRequests.clear();renderArrivalTasks();$('activityArrivalSource').textContent=sourceCard.title;$('activityArrivalSave').disabled=false;}
  catch(error){if(key===arrivalKey)$('activityArrivalError').textContent=error.message;}
 }
 function arrivalControls(value){arrivalBusy=value;$('activityArrivalModal').querySelectorAll('button,input,textarea').forEach(element=>element.disabled=value);}
 async function saveArrival() {
  if(arrivalBusy||!sourceCard)return;arrivalControls(true);$('activityArrivalError').textContent='';
  const activities=[...$('activityArrivalTasks').querySelectorAll('[data-arrival-enabled]:checked')].map(toggle=>{
   const kind=toggle.dataset.arrivalEnabled,readPicker=audience=>{const picker=$(`[data-arrival-picker="${kind}:${audience}"]`),users=arrivalSelectedUsers.get(`${kind}:${audience}`)||new Map(),minimum=picker.querySelector('[data-arrival-minimum]').value;return {role_ids:[...picker.querySelectorAll('[data-arrival-role]:checked')].map(item=>Number(item.dataset.arrivalRole)),user_ids:[...users.keys()],target_min_weight:minimum?Number(minimum):null};};
   const assignees=readPicker('assignees'),recipients=readPicker('recipients');
   return {kind,...assignees,result_recipients:recipients};
  });
  if(!activities.length){arrivalBusy=false;arrivalControls(false);$('activityArrivalError').textContent='Seleziona almeno un’attività da inviare.';return;}
  const incomplete=activities.find(item=>!(item.role_ids.length||item.user_ids.length||item.target_min_weight!==null)||!(item.result_recipients.role_ids.length||item.result_recipients.user_ids.length||item.result_recipients.target_min_weight!==null));
  if(incomplete){arrivalBusy=false;arrivalControls(false);$('activityArrivalError').textContent='Per ogni attività selezionata indica incaricati e destinatari dell’esito.';return;}
  const payload={card_id:sourceCard.id,revision:sourceCard.revision,event_key:arrivalKey,received_on:$('activityArrivalDate').value,partial:$('activityArrivalPartial').checked,note:$('activityArrivalNote').value,activities};
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
   $('activityDetail').onclick=event=>{const action=event.target.closest('[data-activity-action]'),remove=event.target.closest('[data-remove-photo]');if(action)runAction(action.dataset.activityAction);else if(remove)removePhoto(Number(remove.dataset.removePhoto));else if(event.target.closest('#activityPhotoUpload'))upload();else if(event.target.closest('#activityFilesUpload'))uploadFiles();else if(event.target.closest('[data-remove-file]'))removeFile(Number(event.target.closest('[data-remove-file]').dataset.removeFile));};
  });
  $('activityArrivalTasks').addEventListener('change',event=>{
   const user=event.target.closest('[data-arrival-user]');if(user){const picker=user.closest('[data-arrival-picker]'),key=picker.dataset.arrivalPicker,map=arrivalSelectedUsers.get(key)||new Map(),id=Number(user.dataset.arrivalUser),found=arrivalDirectory.users.find(item=>item.id===id);if(user.checked&&found)map.set(id,found);else map.delete(id);arrivalSelectedUsers.set(key,map);}
  });
  $('activityArrivalTasks').addEventListener('input',event=>{const input=event.target.closest('[data-arrival-user-search]');if(input){clearTimeout(input._arrivalTimer);input._arrivalTimer=setTimeout(()=>loadArrivalUsers(input),250);}});
  $('activityModal').addEventListener('hide.bs.modal',event=>{if(busy)event.preventDefault();});
  $('activityModal').addEventListener('hidden.bs.modal',()=>{selected=null;activity=null;detailGeneration++;$('activityDetail').onclick=null;$('activityDetailRefresh').onclick=null;$('activityError').textContent='';});
  const composer=window.ActivityCreate?.init({api,onCreated:async(saved,context={})=>{if(!context.row&&!context.parent){params.delete('arrival');page=1;$('activityStatus').value='active';$('activitySearch').value='';history.replaceState({},'',location.pathname);}await load();if(context.row||context.parent)openDetail(context.row?.id||context.parent.id);}});
  function compose(options){if(!composer)return;const modal=$('activityModal');modal.addEventListener('hidden.bs.modal',()=>composer.open(options),{once:true});bootstrap.Modal.getOrCreateInstance(modal).hide();}
  $('activityDetail').addEventListener('click',event=>{if(busy||!activity)return;if(event.target.closest('[data-edit-activity]'))compose({row:activity});else if(event.target.closest('[data-new-child]'))compose({parent:activity});else {const related=event.target.closest('[data-related-activity]');if(related)openDetail(Number(related.dataset.relatedActivity));}});
  if(isManager){
   $('activityRouting').onclick=()=>{bootstrap.Modal.getOrCreateInstance($('activityRoutingModal')).show();readRouting();};
   $('activityRoutingModal').addEventListener('shown.bs.modal',()=>{routingControls(routingBusy);$('activityRoutingSave').onclick=saveRouting;$('activityRoutingReload').onclick=readRouting;});
   $('activityRoutingModal').addEventListener('hide.bs.modal',event=>{if(routingBusy)event.preventDefault();});
   $('activityRoutingModal').addEventListener('hidden.bs.modal',()=>{routing=null;$('activityRoutingSave').onclick=null;$('activityRoutingReload').onclick=null;});
   $('activityArrivalModal').addEventListener('shown.bs.modal',()=>{$('activityArrivalSave').disabled=!sourceCard||arrivalBusy;$('activityArrivalSave').onclick=saveArrival;});
   $('activityArrivalModal').addEventListener('hide.bs.modal',event=>{if(arrivalBusy)event.preventDefault();});
   $('activityArrivalModal').addEventListener('hidden.bs.modal',()=>{sourceCard=null;arrivalKey=null;$('activityArrivalSave').onclick=null;});
   if(params.get('arrival_card'))openArrival(Number(params.get('arrival_card')));
  }
  const reset=()=>{page=1;load();};$('activityCompleted').onclick=()=>{$('activityStatus').value='completed';params.delete('arrival');history.replaceState({},'',location.pathname+'?status=completed');reset();};$('activityOpen').onclick=()=>{$('activityStatus').value='active';params.delete('arrival');history.replaceState({},'',location.pathname);reset();};if(params.get('status')==='completed')$('activityStatus').value='completed';$('activityRefresh').onclick=()=>{params.delete('arrival');history.replaceState({},'',location.pathname);reset();};$('activityStatus').onchange=reset;
  $('activitySearch').oninput=()=>{clearTimeout(searchTimer);generation++;searchTimer=setTimeout(reset,250);};$('activityPrevious').onclick=()=>{page--;load();};$('activityNext').onclick=()=>{page++;load();};
  load();const timer=setInterval(()=>{if(!document.hidden&&!document.querySelector('.activity-modal.show'))load(true);},30000);window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  if(params.get('activity')&&!(isManager&&params.get('arrival_card')))openDetail(Number(params.get('activity')));
 });
})();

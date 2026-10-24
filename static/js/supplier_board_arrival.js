(() => {
 'use strict';
 const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const kinds={check_goods:'Controllare la merce',lots:'Inviare i lotti',store_goods:'Sistemare i prodotti in magazzino'};
 let card=null,eventKey=null,busy=false,directory={roles:[],users:[]};
 const selectedUsers=new Map(),searchRequests=new Map();
 async function api(url,options={}) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),45000);
  try {
   const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options,signal:controller.signal,headers:{Accept:'application/json','X-Requested-With':'XMLHttpRequest','Content-Type':'application/json',...(options.headers||{})}});
   const result=await response.json().catch(()=>({}));
   if(response.redirected)throw Error('Sessione scaduta. Accedi di nuovo.');
   if(!response.ok||result.ok!==true)throw Error(result.error||`Errore ${response.status}. Aggiorna la bacheca e riprova.`);
   return result;
  } catch(error){if(error.name==='AbortError')throw Error('La richiesta ha impiegato troppo tempo. Aggiorna la bacheca e riprova.');throw error;}
  finally{clearTimeout(timer);}
 }
 function picker(kind,audience,names) {
  const key=`${kind}:${audience}`,legend=audience==='assignees'?'Incaricati':'Destinatari dell’esito';
  const defaults=directory.roles.filter(role=>names.includes(role.name.trim().toLocaleLowerCase('it-IT'))).map(role=>role.id);
  const weights=new Map();directory.roles.forEach(role=>{if(!weights.has(role.weight))weights.set(role.weight,[]);weights.get(role.weight).push(role.name);});
  const options=[...weights].sort((a,b)=>a[0]-b[0]).map(([weight,labels])=>`<option value="${weight}">${esc(labels.join(', '))} e superiori</option>`).join('');
  return `<fieldset class="supplier-arrival-picker" data-arrival-picker="${key}"><legend>${legend}</legend><div class="supplier-arrival-role-list">${directory.roles.map(role=>`<label><input type="checkbox" data-arrival-role="${role.id}" ${defaults.includes(role.id)?'checked':''}> ${esc(role.name)}</label>`).join('')}</div><label for="supplier-arrival-min-${kind}-${audience}">Includi anche i ruoli con peso minimo</label><select id="supplier-arrival-min-${kind}-${audience}" class="form-select" data-arrival-minimum><option value="">Nessuna soglia</option>${options}</select><label for="supplier-arrival-search-${kind}-${audience}">Aggiungi singoli utenti</label><input id="supplier-arrival-search-${kind}-${audience}" class="form-control" type="search" data-arrival-user-search placeholder="Cerca nome utente"><div class="supplier-arrival-user-list" data-arrival-users></div><small data-arrival-users-hint>${directory.users.length} utenti operativi mostrati; cerca per restringere.</small></fieldset>`;
 }
 function renderUsers(kind,audience,users) {
  const key=`${kind}:${audience}`,root=document.querySelector(`#supplierArrivalTasks [data-arrival-picker="${key}"]`);if(!root)return;
  if(!selectedUsers.has(key))selectedUsers.set(key,new Map());
  const chosen=selectedUsers.get(key);
  root.querySelector('[data-arrival-users]').innerHTML=users.map(user=>`<label><input type="checkbox" data-arrival-user="${user.id}" ${chosen.has(user.id)?'checked':''}> ${esc(user.name)}</label>`).join('')||'<small>Nessun utente trovato.</small>';
 }
 function attachmentPicker() {
  const files=card.attachments||[];
  return files.length?`<fieldset class="supplier-arrival-attachments"><legend>Allegati da inviare con questa attività</legend>${files.map(file=>`<label><input type="checkbox" data-arrival-attachment="${esc(file.id)}"> ${esc(file.filename)} ${file.id==='order_pdf'?'<small>PDF ordine</small>':''}</label>`).join('')}</fieldset>`:'<p class="supplier-arrival-no-files">La scheda non contiene allegati.</p>';
 }
 function renderTasks() {
  const staff=['staff'],office=['office','ufficio'];
  const task=(kind,title,custom=false)=>`<section class="supplier-arrival-task" data-arrival-task="${kind}"><label class="supplier-arrival-task-title"><input type="checkbox" data-arrival-enabled="${kind}" ${custom?'':'checked'}><strong>${esc(title)}</strong></label>${custom?'<label for="supplierArrivalCustomTitle" class="form-label">Titolo</label><input id="supplierArrivalCustomTitle" class="form-control" maxlength="200" data-arrival-custom-title placeholder="Es. Preparare la merce per il corriere"><label for="supplierArrivalCustomDescription" class="form-label">Descrizione</label><textarea id="supplierArrivalCustomDescription" class="form-control" rows="2" maxlength="5000" data-arrival-custom-description></textarea>':''}<details><summary>Configura incaricati, allegati e destinatari</summary><div class="supplier-arrival-config">${picker(kind,'assignees',staff)}${attachmentPicker()}${picker(kind,'recipients',office)}</div></details></section>`;
  $('supplierArrivalTasks').innerHTML=Object.entries(kinds).map(([kind,title])=>task(kind,title)).join('')+task('custom_1','Crea un’attività specifica',true);
  for(const kind of [...Object.keys(kinds),'custom_1'])for(const audience of ['assignees','recipients'])renderUsers(kind,audience,directory.users);
 }
 async function loadUsers(input) {
  const root=input.closest('[data-arrival-picker]'),key=root.dataset.arrivalPicker,[kind,audience]=key.split(':'),request=(searchRequests.get(key)||0)+1;searchRequests.set(key,request);
  root.querySelector('[data-arrival-users-hint]').textContent='Ricerca utenti…';
  try {const result=await api('/activities/api/assignees?'+new URLSearchParams({q:input.value.trim()}),{headers:{}});if(searchRequests.get(key)!==request)return;const all=new Map(directory.users.map(user=>[user.id,user]));result.users.forEach(user=>all.set(user.id,user));directory.users=[...all.values()];renderUsers(kind,audience,result.users);root.querySelector('[data-arrival-users-hint]').textContent=`${result.users.length} utenti trovati${result.total>result.users.length?' (restringi la ricerca)':''}.`;}
  catch(error){if(searchRequests.get(key)===request)root.querySelector('[data-arrival-users-hint]').textContent=error.message;}
 }
 function controls(disabled) {
  busy=disabled;$('supplierArrivalModal').querySelectorAll('button,input,textarea,select').forEach(input=>input.disabled=disabled);
 }
 async function saveArrival() {
  if(busy||!card)return;
  controls(true);$('supplierArrivalError').textContent='';const button=$('supplierArrivalSave'),label=button.textContent;button.textContent='Invio attività…';
  try {
   const activities=[...$('supplierArrivalTasks').querySelectorAll('[data-arrival-enabled]:checked')].map(toggle=>{
    const kind=toggle.dataset.arrivalEnabled,task=toggle.closest('[data-arrival-task]');
    const read=audience=>{const root=$(`supplierArrivalTasks`).querySelector(`[data-arrival-picker="${kind}:${audience}"]`),users=selectedUsers.get(`${kind}:${audience}`)||new Map(),minimum=root.querySelector('[data-arrival-minimum]').value;return {role_ids:[...root.querySelectorAll('[data-arrival-role]:checked')].map(input=>Number(input.dataset.arrivalRole)),user_ids:[...users.keys()],target_min_weight:minimum?Number(minimum):null};};
    const attachment_ids=[...task.querySelectorAll('[data-arrival-attachment]:checked')].map(input=>/^\d+$/.test(input.dataset.arrivalAttachment)?Number(input.dataset.arrivalAttachment):input.dataset.arrivalAttachment);
    return {kind,...read('assignees'),result_recipients:read('recipients'),attachment_ids,...(kind==='custom_1'?{title:$('supplierArrivalCustomTitle').value,description:$('supplierArrivalCustomDescription').value}:{})};
   });
   if(!activities.length)throw Error('Seleziona almeno un’attività da inviare.');
   if(activities.some(item=>!(item.role_ids.length||item.user_ids.length||item.target_min_weight!==null)||!(item.result_recipients.role_ids.length||item.result_recipients.user_ids.length||item.result_recipients.target_min_weight!==null)))throw Error('Per ogni attività selezionata indica incaricati e destinatari dell’esito.');
   const payload={card_id:card.id,revision:card.revision,event_key:eventKey,received_on:$('supplierArrivalDate').value,partial:$('supplierArrivalPartial').checked,note:$('supplierArrivalNote').value,activities};
   await api('/activities/api/supplier-arrivals',{method:'POST',body:JSON.stringify(payload)});
   bootstrap.Modal.getInstance($('supplierArrivalModal')).hide();$('supplierRefresh').click();
  } catch(error){$('supplierArrivalError').textContent=error.message;}
  finally{button.textContent=label;controls(false);}
 }
 async function open(cardId) {
  card=null;eventKey=crypto.randomUUID?crypto.randomUUID():[...crypto.getRandomValues(new Uint8Array(16))].map(value=>value.toString(16).padStart(2,'0')).join('');
  const now=new Date();selectedUsers.clear();searchRequests.clear();$('supplierArrivalDate').value=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');$('supplierArrivalNote').value='';$('supplierArrivalPartial').checked=false;$('supplierArrivalError').textContent='';$('supplierArrivalSource').textContent='Caricamento scheda…';$('supplierArrivalTasks').replaceChildren();$('supplierArrivalSave').disabled=true;
  bootstrap.Modal.getOrCreateInstance($('supplierArrivalModal')).show();
  try {const [source,people]=await Promise.all([api(`/activities/api/source-card/${cardId}`),api('/activities/api/assignees')]);card=source.card;directory=people;renderTasks();$('supplierArrivalSource').textContent=card.title;$('supplierArrivalSave').disabled=false;}
  catch(error){$('supplierArrivalError').textContent=error.message;}
 }
 document.addEventListener('DOMContentLoaded',()=>{
  const modal=$('supplierArrivalModal'),cardModal=$('supplierCardModal');document.body.appendChild(modal);
  modal.addEventListener('show.bs.modal',()=>document.body.classList.add('supplier-arrival-modal-open'));
  modal.addEventListener('hidden.bs.modal',()=>{document.body.classList.remove('supplier-arrival-modal-open');card=null;eventKey=null;});
  modal.addEventListener('shown.bs.modal',()=>{$('supplierArrivalSave').onclick=saveArrival;});
  modal.addEventListener('hide.bs.modal',event=>{if(busy)event.preventDefault();});
  $('supplierCardArrival').addEventListener('click',event=>{
   event.preventDefault();const cardId=Number(event.currentTarget.dataset.cardId);if(!cardId)return;
   cardModal.addEventListener('hidden.bs.modal',()=>open(cardId),{once:true});bootstrap.Modal.getOrCreateInstance(cardModal).hide();
  });
  $('supplierArrivalTasks').addEventListener('change',event=>{
   const user=event.target.closest('[data-arrival-user]');if(!user)return;
   const root=user.closest('[data-arrival-picker]'),key=root.dataset.arrivalPicker,map=selectedUsers.get(key)||new Map(),id=Number(user.dataset.arrivalUser),found=directory.users.find(item=>item.id===id);
   if(user.checked&&found)map.set(id,found);else map.delete(id);selectedUsers.set(key,map);
  });
  $('supplierArrivalTasks').addEventListener('input',event=>{
   if(event.target.matches('[data-arrival-user-search]')){clearTimeout(event.target._arrivalTimer);event.target._arrivalTimer=setTimeout(()=>loadUsers(event.target),250);}
   if(event.target.matches('[data-arrival-custom-title],[data-arrival-custom-description]'))$('supplierArrivalTasks').querySelector('[data-arrival-enabled="custom_1"]').checked=true;
  });
 });
})();

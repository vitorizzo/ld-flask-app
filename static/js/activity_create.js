(() => {
 'use strict';
 window.ActivityCreate={init({api,onCreated}) {
  const $=id=>document.getElementById(id),modal=$('activityCreateModal');if(!modal)return;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let key=null,busy=false,context={};
  function controls(){modal.querySelectorAll('button,input,textarea,select').forEach(el=>el.disabled=busy);$('activityCreateSave').disabled=busy||!assignment.loaded||!result.loaded;}
  function picker(prefix){
   const el=suffix=>$(prefix+suffix);
   let selected=new Map(),shown=[],generation=0,timer,loaded=false;
   function selections(){
    el('SelectedUsers').innerHTML=[...selected.values()].map(user=>`<button class="btn btn-sm btn-outline-secondary m-1" type="button" data-unselect="${user.id}" aria-label="Rimuovi ${esc(user.name)}">${esc(user.name)} ×</button>`).join('');
    el('NewUsers').querySelectorAll('[data-user]').forEach(input=>input.checked=selected.has(Number(input.dataset.user)));
    el('UsersHint').textContent=selected.size+' utenti selezionati';controls();
   }
   async function users(initial=false){
    const request=++generation;el('UsersHint').textContent='Caricamento utenti…';
    try{
     const data=await api('/activities/api/assignees?'+new URLSearchParams({role_id:el('UserRole').value,q:el('UserSearch').value,...(context.parent?{parent_id:context.parent.id}:{})}));
     if(request!==generation||!key)return;
     if(initial){
      el('NewRoles').innerHTML=data.roles.map(role=>`<label class="activity-checkbox"><input type="checkbox" data-role="${role.id}"> ${esc(role.name)}</label>`).join('');
      el('UserRole').innerHTML='<option value="">Tutti i ruoli operativi</option>'+data.roles.map(role=>`<option value="${role.id}">${esc(role.name)}</option>`).join('');
      const weights=new Map();data.roles.forEach(role=>{if(!weights.has(role.weight))weights.set(role.weight,[]);weights.get(role.weight).push(role.name);});
      const seed=prefix==='activity'?context.row:context.row?.result_recipients;if(seed?.target_min_weight!=null&&!weights.has(seed.target_min_weight))weights.set(seed.target_min_weight,[]);
      el('MinWeight').innerHTML='<option value="">Nessuna soglia minima</option>'+[...weights].sort((a,b)=>a[0]-b[0]).map(([weight,names])=>`<option value="${weight}">${weight} — ${esc(names.join(', '))} e superiori</option>`).join('');
     }
     shown=data.users;el('NewUsers').innerHTML=shown.map(user=>`<label class="activity-checkbox"><input type="checkbox" data-user="${user.id}"> ${esc(user.name)}</label>`).join('')||'<p>Nessun utente trovato.</p>';
     if(initial){const seed=prefix==='activity'?context.row:context.row?.result_recipients;el('NewRoles').querySelectorAll('[data-role]').forEach(input=>input.checked=(seed?.role_ids||[]).includes(Number(input.dataset.role)));el('MinWeight').value=seed?.target_min_weight==null?'':String(seed.target_min_weight);}
     loaded=true;selections();el('UsersHint').textContent+=` · ${data.total} trovati${data.total>shown.length?' (primi 100: restringi la ricerca)':''}`;
    }catch(error){if(request===generation){$('activityCreateError').textContent=error.message;el('UsersHint').textContent='Aggiorna la ricerca per riprovare.';}}
   }
   el('UserRole').onchange=()=>users(!loaded);
   el('UserSearch').oninput=()=>{clearTimeout(timer);generation++;timer=setTimeout(()=>users(!loaded),250);};
   el('NewUsers').onchange=event=>{const id=Number(event.target.dataset.user),user=shown.find(row=>row.id===id);if(!user)return;if(event.target.checked)selected.set(id,user);else selected.delete(id);selections();};
   el('UsersSelect').onclick=()=>{shown.forEach(user=>selected.set(user.id,user));selections();};
   el('SelectedUsers').onclick=event=>{const button=event.target.closest('[data-unselect]');if(button){selected.delete(Number(button.dataset.unselect));selections();}};
   return {get loaded(){return loaded;},reset(seed){selected=new Map((seed?.users||[]).map(u=>[u.id,u]));shown=[];loaded=false;generation++;clearTimeout(timer);['NewRoles','NewUsers','SelectedUsers'].forEach(id=>el(id).innerHTML='');['MinWeight','UserRole','UserSearch'].forEach(id=>el(id).value='');},load:()=>users(true),stop(){generation++;clearTimeout(timer);},payload(){return {role_ids:[...el('NewRoles').querySelectorAll('[data-role]:checked')].map(input=>Number(input.dataset.role)),user_ids:[...selected.keys()],target_min_weight:el('MinWeight').value?Number(el('MinWeight').value):null};}};
  }
  const assignment=picker('activity'),result=picker('activityResult');
  const valid=p=>p.role_ids.length||p.user_ids.length||p.target_min_weight!==null;
  function open(options={}){
   context=options;
   if($('activityCreationFiles'))$('activityCreationFiles').hidden=!!context.row;
   $('activityCreateTitle').textContent=context.row?'Modifica attività':context.parent?'Nuova sottoattività':'Nuova attività';
   $('activityCreateSave').textContent=context.row?'Salva modifiche':'Crea attività';
   if($('activityCreateContext'))$('activityCreateContext').textContent=context.parent?'Sottoattività di: '+context.parent.title:context.row?.completed_at?'Le modifiche saranno segnalate ai destinatari dell’esito.':'';
   if($('activitySharedFiles'))$('activitySharedFiles').innerHTML=context.parent?'<fieldset><legend class="fs-6">Condividi allegati della principale</legend>'+[...(context.parent.attachments||[]).map(f=>({id:f.id,label:f.filename,type:'file'})),...(context.parent.photos||[]).map(f=>({id:f.id,label:f.label,type:'photo'}))].map(f=>`<label class="activity-checkbox"><input type="checkbox" data-share-type="${f.type}" data-share-id="${f.id}"> ${esc(f.label)}</label>`).join('')+'</fieldset>':'';
   key=crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
   assignment.reset(context.row);result.reset(context.row?.result_recipients);$('activityNewTitle').value=context.row?.title||'';$('activityNewDescription').value=context.row?.description||'';$('activityNewFiles').value='';$('activityCreateError').textContent='';
   bootstrap.Modal.getOrCreateInstance(modal).show();assignment.load();result.load();
  }
  if($('activityNew'))$('activityNew').onclick=()=>open();
  async function save(){
   if(busy||!assignment.loaded||!result.loaded)return;
   const payload={title:$('activityNewTitle').value.trim(),description:$('activityNewDescription').value.trim(),...assignment.payload(),result_recipients:result.payload(),client_key:key};
   if(!payload.title||!valid(payload)||!valid(payload.result_recipients)){$('activityCreateError').textContent='Inserisci titolo, incaricati e destinatari dell’esito.';return;}
   if(context.parent){payload.parent_id=context.parent.id;payload.parent_revision=context.parent.revision;payload.share_attachment_ids=[];payload.share_photo_ids=[];$('activitySharedFiles').querySelectorAll('[data-share-id]:checked').forEach(input=>payload[input.dataset.shareType==='photo'?'share_photo_ids':'share_attachment_ids'].push(Number(input.dataset.shareId)));}
   if(context.row)payload.revision=context.row.revision;
   const body=new FormData();body.set('data',JSON.stringify(payload));for(const file of $('activityNewFiles').files)body.append('files',file);
   busy=true;controls();$('activityCreateError').textContent='';
   try{const data=await api(context.row?'/activities/api/'+context.row.id:'/activities/api',{method:context.row?'PUT':'POST',body:context.row?JSON.stringify(payload):body});const savedContext=context;busy=false;controls();const hidden=new Promise(resolve=>modal.addEventListener('hidden.bs.modal',resolve,{once:true}));bootstrap.Modal.getOrCreateInstance(modal).hide();await hidden;await onCreated(data.activity,savedContext);}
   catch(error){$('activityCreateError').textContent=error.message;}finally{busy=false;controls();}
  }
  modal.addEventListener('shown.bs.modal',()=>{controls();$('activityCreateSave').onclick=save;$('activityNewTitle').focus();});
  modal.addEventListener('hide.bs.modal',event=>{if(busy)event.preventDefault();});
  modal.addEventListener('hidden.bs.modal',()=>{key=null;assignment.stop();result.stop();$('activityCreateSave').onclick=null;});
  return {open};
 }};
})();

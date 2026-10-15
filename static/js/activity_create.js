(() => {
 'use strict';
 window.ActivityCreate={init({api,onCreated}) {
  const $=id=>document.getElementById(id),modal=$('activityCreateModal');if(!modal)return;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let key=null,busy=false;
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
     const data=await api('/activities/api/assignees?'+new URLSearchParams({role_id:el('UserRole').value,q:el('UserSearch').value}));
     if(request!==generation||!key)return;
     if(initial){
      el('NewRoles').innerHTML=data.roles.map(role=>`<label class="activity-checkbox"><input type="checkbox" data-role="${role.id}"> ${esc(role.name)}</label>`).join('');
      el('UserRole').innerHTML='<option value="">Tutti i ruoli operativi</option>'+data.roles.map(role=>`<option value="${role.id}">${esc(role.name)}</option>`).join('');
      const weights=new Map();data.roles.forEach(role=>{if(!weights.has(role.weight))weights.set(role.weight,[]);weights.get(role.weight).push(role.name);});
      el('MinWeight').innerHTML='<option value="">Nessuna soglia minima</option>'+[...weights].sort((a,b)=>a[0]-b[0]).map(([weight,names])=>`<option value="${weight}">${weight} — ${esc(names.join(', '))} e superiori</option>`).join('');
     }
     shown=data.users;el('NewUsers').innerHTML=shown.map(user=>`<label class="activity-checkbox"><input type="checkbox" data-user="${user.id}"> ${esc(user.name)}</label>`).join('')||'<p>Nessun utente trovato.</p>';
     loaded=true;selections();el('UsersHint').textContent+=` · ${data.total} trovati${data.total>shown.length?' (primi 100: restringi la ricerca)':''}`;
    }catch(error){if(request===generation){$('activityCreateError').textContent=error.message;el('UsersHint').textContent='Aggiorna la ricerca per riprovare.';}}
   }
   el('UserRole').onchange=()=>users(!loaded);
   el('UserSearch').oninput=()=>{clearTimeout(timer);generation++;timer=setTimeout(()=>users(!loaded),250);};
   el('NewUsers').onchange=event=>{const id=Number(event.target.dataset.user),user=shown.find(row=>row.id===id);if(!user)return;if(event.target.checked)selected.set(id,user);else selected.delete(id);selections();};
   el('UsersSelect').onclick=()=>{shown.forEach(user=>selected.set(user.id,user));selections();};
   el('SelectedUsers').onclick=event=>{const button=event.target.closest('[data-unselect]');if(button){selected.delete(Number(button.dataset.unselect));selections();}};
   return {get loaded(){return loaded;},reset(){selected=new Map();shown=[];loaded=false;generation++;clearTimeout(timer);['NewRoles','NewUsers','SelectedUsers'].forEach(id=>el(id).innerHTML='');['MinWeight','UserRole','UserSearch'].forEach(id=>el(id).value='');},load:()=>users(true),stop(){generation++;clearTimeout(timer);},payload(){return {role_ids:[...el('NewRoles').querySelectorAll('[data-role]:checked')].map(input=>Number(input.dataset.role)),user_ids:[...selected.keys()],target_min_weight:el('MinWeight').value?Number(el('MinWeight').value):null};}};
  }
  const assignment=picker('activity'),result=picker('activityResult');
  const valid=p=>p.role_ids.length||p.user_ids.length||p.target_min_weight!==null;
  $('activityNew').onclick=()=>{
   key=crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
   assignment.reset();result.reset();$('activityNewTitle').value='';$('activityNewDescription').value='';$('activityNewFiles').value='';$('activityCreateError').textContent='';
   bootstrap.Modal.getOrCreateInstance(modal).show();assignment.load();result.load();
  };
  async function save(){
   if(busy||!assignment.loaded||!result.loaded)return;
   const payload={title:$('activityNewTitle').value.trim(),description:$('activityNewDescription').value.trim(),...assignment.payload(),result_recipients:result.payload(),client_key:key};
   if(!payload.title||!valid(payload)||!valid(payload.result_recipients)){$('activityCreateError').textContent='Inserisci titolo, incaricati e destinatari dell’esito.';return;}
   const body=new FormData();body.set('data',JSON.stringify(payload));for(const file of $('activityNewFiles').files)body.append('files',file);
   busy=true;controls();$('activityCreateError').textContent='';
   try{await api('/activities/api',{method:'POST',body});busy=false;controls();bootstrap.Modal.getOrCreateInstance(modal).hide();await onCreated();}
   catch(error){$('activityCreateError').textContent=error.message;}finally{busy=false;controls();}
  }
  modal.addEventListener('shown.bs.modal',()=>{controls();$('activityCreateSave').onclick=save;$('activityNewTitle').focus();});
  modal.addEventListener('hide.bs.modal',event=>{if(busy)event.preventDefault();});
  modal.addEventListener('hidden.bs.modal',()=>{key=null;assignment.stop();result.stop();$('activityCreateSave').onclick=null;});
 }};
})();

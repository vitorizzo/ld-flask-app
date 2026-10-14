(() => {
 'use strict';
 window.ActivityCreate={init({api,onCreated}) {
  const $=id=>document.getElementById(id),modal=$('activityCreateModal');if(!modal)return;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let selected=new Map(),shown=[],key=null,busy=false,loaded=false,generation=0,timer;
  function controls(){modal.querySelectorAll('button,input,textarea,select').forEach(el=>el.disabled=busy);$('activityCreateSave').disabled=busy||!loaded;}
  function selections(){
   $('activitySelectedUsers').innerHTML=[...selected.values()].map(user=>`<button class="btn btn-sm btn-outline-secondary m-1" type="button" data-unselect="${user.id}" aria-label="Rimuovi ${esc(user.name)}">${esc(user.name)} ×</button>`).join('');
   $('activityNewUsers').querySelectorAll('[data-user]').forEach(el=>el.checked=selected.has(Number(el.dataset.user)));controls();
  }
  async function users(initial=false){
   const request=++generation;$('activityUsersHint').textContent='Caricamento utenti…';
   if(initial){loaded=false;controls();}
   try {
    const query=new URLSearchParams({role_id:$('activityUserRole').value,q:$('activityUserSearch').value});
    const data=await api('/activities/api/assignees?'+query);if(request!==generation||!key)return;
    if(initial){$('activityNewRoles').innerHTML=data.roles.map(role=>`<label class="activity-checkbox"><input type="checkbox" data-role="${role.id}"> ${esc(role.name)}</label>`).join('');$('activityUserRole').innerHTML='<option value="">Tutti i ruoli operativi</option>'+data.roles.map(role=>`<option value="${role.id}">${esc(role.name)}</option>`).join('');}
    shown=data.users;$('activityNewUsers').innerHTML=shown.map(user=>`<label class="activity-checkbox"><input type="checkbox" data-user="${user.id}"> ${esc(user.name)}</label>`).join('')||'<p>Nessun utente trovato.</p>';
    loaded=true;selections();$('activityUsersHint').textContent=`${selected.size} utenti selezionati · ${data.total} trovati${data.total>shown.length?' (primi 100: restringi la ricerca)':''}`;
    $('activityCreateError').textContent='';
   }catch(error){if(request===generation){$('activityCreateError').textContent=error.message;$('activityUsersHint').textContent='Aggiorna la ricerca per riprovare.';}}
  }
  $('activityNew').onclick=()=>{
   selected=new Map();shown=[];key=crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
   $('activityNewTitle').value='';$('activityNewDescription').value='';$('activityUserRole').value='';$('activityUserSearch').value='';$('activityNewRoles').innerHTML='';$('activityNewUsers').innerHTML='';$('activitySelectedUsers').innerHTML='';$('activityCreateError').textContent='';
   bootstrap.Modal.getOrCreateInstance(modal).show();users(true);
  };
  $('activityUserRole').onchange=()=>users(!loaded);
  $('activityUserSearch').oninput=()=>{clearTimeout(timer);generation++;timer=setTimeout(()=>users(!loaded),250);};
  $('activityNewUsers').onchange=event=>{const id=Number(event.target.dataset.user),user=shown.find(row=>row.id===id);if(!user)return;if(event.target.checked)selected.set(id,user);else selected.delete(id);selections();$('activityUsersHint').textContent=`${selected.size} utenti selezionati`;};
  $('activityUsersSelect').onclick=()=>{shown.forEach(user=>selected.set(user.id,user));selections();$('activityUsersHint').textContent=`${selected.size} utenti selezionati`;};
  $('activitySelectedUsers').onclick=event=>{const button=event.target.closest('[data-unselect]');if(button){selected.delete(Number(button.dataset.unselect));selections();$('activityUsersHint').textContent=`${selected.size} utenti selezionati`;}};
  $('activityCreateSave').onclick=async()=>{
   if(busy||!loaded)return;
   const payload={title:$('activityNewTitle').value.trim(),description:$('activityNewDescription').value.trim(),role_ids:[...$('activityNewRoles').querySelectorAll('[data-role]:checked')].map(el=>Number(el.dataset.role)),user_ids:[...selected.keys()],client_key:key};
   if(!payload.title||(!payload.role_ids.length&&!payload.user_ids.length)){$('activityCreateError').textContent='Inserisci il titolo e scegli almeno un ruolo o un utente.';return;}
   busy=true;controls();$('activityCreateError').textContent='';
   try{await api('/activities/api',{method:'POST',body:JSON.stringify(payload)});busy=false;controls();bootstrap.Modal.getOrCreateInstance(modal).hide();await onCreated();}
   catch(error){$('activityCreateError').textContent=error.message;}
   finally{busy=false;controls();}
  };
  modal.addEventListener('shown.bs.modal',()=>{controls();$('activityNewTitle').focus();});
  modal.addEventListener('hide.bs.modal',event=>{if(busy)event.preventDefault();});
  modal.addEventListener('hidden.bs.modal',()=>{key=null;generation++;clearTimeout(timer);});
 }};
})();

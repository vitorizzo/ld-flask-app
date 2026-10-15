(() => {
 const box=document.getElementById('homeActivities');if(!box)return;
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let inFlight=false;
 async function refresh(){
  if(inFlight)return;inFlight=true;
  try {
   const response=await fetch('/activities/api/summary',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
   const data=await response.json();if(!response.ok||data.ok===false)throw Error('Attività temporaneamente non disponibili.');
   box.hidden=!(data.count>0||data.results?.count>0||box.dataset.operational==='1');
   document.getElementById('homeActivityCount').textContent=`(${data.count}) · Esiti nuovi: ${data.results?.count||0}`;
   const groups=new Map();data.rows.forEach(row=>{const key=row.source?'arrival-'+row.source.id:'activity-'+row.id;if(!groups.has(key))groups.set(key,{label:row.source?.label||'Attività',rows:[]});groups.get(key).rows.push(row);});
   const pending=data.rows.length?'<ul>'+[...groups.values()].map(group=>`<li><strong>${esc(group.label)}</strong><ul>${group.rows.map(row=>`<li><a data-home-activity="${row.id}" href="/activities?activity=${row.id}">${esc(row.title)}</a>${row.owner?' · In carico a '+esc(row.owner):''}${data.sees_all?'<br><small>'+esc(ActivityRecipients(row))+'</small>':''}</li>`).join('')}</ul></li>`).join('')+'</ul>':'<p>Non ci sono attività aperte per '+(data.sees_all?'il team':'te')+'.</p>';
   const markup=pending+(data.results?.rows.length?'<h3 class="fs-6">Esiti ricevuti</h3><ul>'+data.results.rows.map(row=>`<li><a href="/activities?activity=${row.activity_id}">${esc(row.title)}</a>${row.action==='updated'?' · Modificata dopo il completamento':''} · ${esc({completed:'Completata',not_required:'Non necessario',cancelled:'Annullata'}[row.status]||row.status)}</li>`).join('')+'</ul>':'');
   if(document.getElementById('homeActivitySummary').innerHTML!==markup)document.getElementById('homeActivitySummary').innerHTML=markup;
  } catch(error){if(box.dataset.operational==='1'){box.hidden=false;document.getElementById('homeActivitySummary').textContent='Attività temporaneamente non disponibili.';}}
  finally{inFlight=false;}
 }
 refresh();const timer=setInterval(()=>{if(!document.hidden)refresh();},60000);window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();

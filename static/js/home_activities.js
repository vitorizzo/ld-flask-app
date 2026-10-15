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
   const ids=new Set(data.rows.map(r=>r.id)),children=new Map(),roots=[];
   data.rows.forEach(row=>{if(row.parent_id&&ids.has(row.parent_id)){if(!children.has(row.parent_id))children.set(row.parent_id,[]);children.get(row.parent_id).push(row);}else roots.push(row);});
   const done=row=>['completed','not_required'].includes(row.status);
   function branch(row){const sub=(children.get(row.id)||[]).sort((a,b)=>Number(done(b))-Number(done(a))||(a.completed_at||'').localeCompare(b.completed_at||'')||a.id-b.id);
    return '<li class="activity-tree-node '+(done(row)&&row.parent_id?'is-pinned':'')+'"><div class="activity-row"><div>'+ActivityTree.title(row,(done(row)&&row.parent_id?'📌 ':'')+esc(row.title),sub.length)+'<br><a data-home-activity="'+row.id+'" href="/activities?activity='+row.id+'">Apri attività</a> · '+esc({pending:'Da fare',in_progress:'In corso',completed:'Completata',not_required:'Non necessario',cancelled:'Annullata'}[row.status]||row.status)+(row.owner?' · In carico a '+esc(row.owner):'')+(data.sees_all?'<br><small>'+esc(ActivityRecipients(row))+'</small>':'')+'</div></div>'+(sub.length?'<ul class="activity-tree"'+ActivityTree.hidden(row.id)+'>'+sub.map(branch).join('')+'</ul>':'')+'</li>';}
   const pending=roots.length?'<ul class="activity-tree">'+roots.map(branch).join('')+'</ul>':'<p>Non ci sono attività aperte per '+(data.sees_all?'il team':'te')+'.</p>';
   const markup=pending+(data.results?.rows.length?'<h3 class="fs-6">Esiti ricevuti</h3><ul>'+data.results.rows.map(row=>`<li><a href="/activities?activity=${row.activity_id}">${esc(row.title)}</a>${row.action==='updated'?' · Modificata dopo il completamento':''} · ${esc({completed:'Completata',not_required:'Non necessario',cancelled:'Annullata'}[row.status]||row.status)}</li>`).join('')+'</ul>':'');
   if(document.getElementById('homeActivitySummary').innerHTML!==markup)document.getElementById('homeActivitySummary').innerHTML=markup;
  } catch(error){if(box.dataset.operational==='1'){box.hidden=false;document.getElementById('homeActivitySummary').textContent='Attività temporaneamente non disponibili.';}}
  finally{inFlight=false;}
 }
 refresh();const timer=setInterval(()=>{if(!document.hidden)refresh();},60000);window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();

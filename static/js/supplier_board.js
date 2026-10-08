(() => {
 const $ = id => document.getElementById(id);
 const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let data = {columns:[],cards:[]}, editing = null, saving = false, generation = 0, searchTimer, searchGeneration = 0, dragId = null;
 async function api(url, options={}) {
  const res = await fetch(url, {credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},...options});
  const json = await res.json().catch(()=>({}));
  if (!res.ok || json.ok === false) throw Error(json.error || `HTTP ${res.status}`);
  return json;
 }
 const options = current => data.columns.map(c=>`<option value="${c.id}" ${c.id===current?'selected':''}>${esc(c.name)}</option>`).join('');
 function render() {
  const query = $('supplierFilter').value.trim().toLocaleLowerCase();
  const cards = data.cards.filter(card=>[card.title,card.supplier_name,card.reference,card.notes].some(value=>String(value||'').toLocaleLowerCase().includes(query)));
  $('supplierColumnTabs').innerHTML = data.columns.map(column=>`<button type="button" data-column-tab="${column.id}">${esc(column.name)} (${cards.filter(card=>card.column_id===column.id).length})</button>`).join('');
  $('supplierColumns').innerHTML = data.columns.map(column=>`<div class="kiosk-col" data-supplier-column="${column.id}"><div class="kiosk-col__head"><div class="kiosk-col__title">${esc(column.name)}</div><span class="kiosk-col__count">${cards.filter(card=>card.column_id===column.id).length}</span></div><div class="kiosk-col__body">${cards.filter(card=>card.column_id===column.id).map(card=>`
   <article class="order-card supplier-card" data-card="${card.id}" tabindex="0" aria-label="Apri ${esc(card.title)}" draggable="${!matchMedia('(pointer: coarse)').matches}">
    <h2>${esc(card.title)}</h2>${card.supplier_name?`<div class="supplier-card-meta">${esc(card.supplier_name)}</div>`:''}
    ${card.expected_date?`<div class="supplier-card-meta">Arrivo: ${esc(card.expected_date.split('-').reverse().join('/'))}</div>`:''}${card.reference?`<div class="supplier-card-meta">Rif. ${esc(card.reference)}</div>`:''}
    ${card.notes?`<p>${esc(card.notes.slice(0,180))}${card.notes.length>180?'…':''}</p>`:''}${card.is_archived?'<span class="badge bg-secondary">Archiviata</span>':''}
    ${card.order_pdf_url?`<a class="supplier-card-pdf-link" href="${esc(card.order_pdf_url)}" target="_blank" rel="noopener">PDF ordine allegato</a>`:''}
    <div class="supplier-card-footer"><label class="visually-hidden" for="supplierMove${card.id}">Sposta ${esc(card.title)}</label><select class="form-select" id="supplierMove${card.id}" data-move="${card.id}">${options(card.column_id)}</select></div>
   </article>`).join('') || '<div class="kiosk-empty">Nessuna scheda</div>'}</div></div>`).join('');
  $('supplierColumnTabs').querySelectorAll('button').forEach(button=>button.onclick=()=>{
   $('supplierColumns').querySelector(`[data-supplier-column="${button.dataset.columnTab}"]`).scrollIntoView({behavior:'smooth',block:'nearest',inline:'start'});
   $('supplierColumnTabs').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
  });
  $('supplierColumns').querySelectorAll('[data-card]').forEach(element=>{
   const card = data.cards.find(c=>c.id===Number(element.dataset.card));
   element.onclick = event=>{if(!event.target.closest('select,label,a'))openCard(card);};
   element.onkeydown = event=>{if(event.target===element && ['Enter',' '].includes(event.key)){event.preventDefault();openCard(card);}};
   element.ondragstart = event=>{if(event.target.closest('select')){event.preventDefault();return;}dragId=card.id;event.dataTransfer.setData('text/plain',String(card.id));};
   element.ondragend = ()=>dragId=null;
  });
  $('supplierColumns').querySelectorAll('[data-move]').forEach(select=>select.onchange=async()=>{select.disabled=true;await moveCard(Number(select.dataset.move),Number(select.value));});
  $('supplierColumns').querySelectorAll('[data-supplier-column]').forEach(column=>{
   column.ondragover = event=>{if(dragId)event.preventDefault();};
   column.ondrop = event=>{event.preventDefault();if(dragId)moveCard(dragId,Number(column.dataset.supplierColumn));dragId=null;};
  });
 }
 async function reload() {
  const request = ++generation;
  try {const result=await api('/supplier-orders/api/board'+($('supplierArchived').checked?'?archived=1':''));if(request!==generation)return;data=result;render();$('supplierFeedback').textContent='';}
  catch(error){if(request===generation)$('supplierFeedback').textContent=error.message;}
 }
 async function moveCard(id,columnId) {
  try {await api(`/supplier-orders/api/board/cards/${id}`,{method:'PUT',body:JSON.stringify({column_id:columnId})});await reload();}
  catch(error){$('supplierFeedback').textContent=error.message;render();}
 }
 function openCard(card=null) {
  editing = card;
  $('supplierCardPdf').hidden = !card?.order_pdf_url;
  if (card?.order_pdf_url) {
   $('supplierCardPdfOpen').href = card.order_pdf_url;
   $('supplierCardPdfDownload').href = card.order_pdf_url+'?download=1';
  } else {
   $('supplierCardPdfOpen').removeAttribute('href'); $('supplierCardPdfDownload').removeAttribute('href');
  }
  const lines = card?.order_lines || [];
  $('supplierCardOrderLines').hidden = !lines.length;
  $('supplierCardOrderLines').innerHTML = lines.length ? '<h6>Prodotti ordinati</h6>' + lines.map(line => `<p><strong>${esc(line.description)}</strong><br>${esc(line.matrix_code)}${line.subgroup_name ? ' · '+esc(line.subgroup_name) : ''}<br>Da ordinare: <strong>${esc(line.quantity)}</strong> · Giacenza alla creazione: ${esc(line.stock_at_order)}</p>`).join('') : '';
  $('supplierCardTitle').textContent=card?'Modifica scheda':'Nuova scheda fornitore';
  $('supplierCardName').value=card?.title||'';$('supplierCardNotes').value=card?.notes||'';$('supplierCardReference').value=card?.reference||'';$('supplierCardDate').value=card?.expected_date||'';
  $('supplierCardColumn').innerHTML=options(card?.column_id||data.columns[0]?.id);
  $('supplierSearch').value='';$('supplierRegistry').innerHTML='<option value="">Senza collegamento alla Rubrica</option>'+(card?.supplier_id?`<option value="${card.supplier_id}" selected>${esc(card.supplier_name)}</option>`:'');
  $('supplierCardError').textContent='';$('supplierCardArchive').hidden=!card;
  $('supplierCardArchive').textContent=card?.is_archived?'Ripristina scheda':'Archivia scheda';
  bootstrap.Modal.getOrCreateInstance($('supplierCardModal')).show();
 }
 async function searchSuppliers() {
  const request=++searchGeneration;
  const current=$('supplierRegistry').selectedOptions[0];
  try {
   const result=await api('/registry/api/registries?kind=supplier&compact=1&q='+encodeURIComponent($('supplierSearch').value));
   if(request!==searchGeneration)return;
   const suppliers=result.registries||[];
   if(current?.value && !suppliers.some(s=>String(s.id)===current.value))suppliers.unshift({id:current.value,display_name:current.textContent});
   $('supplierRegistry').innerHTML='<option value="">Senza collegamento alla Rubrica</option>'+suppliers.map(s=>`<option value="${s.id}" ${String(s.id)===current?.value?'selected':''}>${esc(s.display_name)}</option>`).join('');
  } catch(error){if(request===searchGeneration)$('supplierCardError').textContent=error.message;}
 }
 async function saveCard(archive=false) {
  if(saving)return;
  if(!$('supplierCardName').value.trim()){$('supplierCardError').textContent='Inserisci il titolo della scheda.';return;}
  saving=true;$('supplierCardSave').disabled=true;$('supplierCardArchive').disabled=true;$('supplierCardError').textContent='';
  const payload={title:$('supplierCardName').value,notes:$('supplierCardNotes').value,reference:$('supplierCardReference').value,expected_date:$('supplierCardDate').value,column_id:Number($('supplierCardColumn').value),supplier_id:$('supplierRegistry').value?Number($('supplierRegistry').value):null,is_archived:archive?!editing?.is_archived:editing?.is_archived||false};
  try {
   await api('/supplier-orders/api/board/cards'+(editing?`/${editing.id}`:''),{method:editing?'PUT':'POST',body:JSON.stringify(payload)});
   saving=false;bootstrap.Modal.getInstance($('supplierCardModal')).hide();await reload();
  } catch(error){$('supplierCardError').textContent=error.message;}
  finally{saving=false;$('supplierCardSave').disabled=false;$('supplierCardArchive').disabled=false;}
 }
 document.addEventListener('DOMContentLoaded',()=>{
  const cardModal = $('supplierCardModal');
  if (cardModal.parentElement !== document.body) document.body.appendChild(cardModal);
  cardModal.addEventListener('show.bs.modal',()=>document.body.classList.add('supplier-card-modal-open'));
  $('supplierNew').onclick=()=>openCard();$('supplierRefresh').onclick=reload;$('supplierFilter').oninput=render;$('supplierArchived').onchange=reload;
  $('supplierSearch').oninput=()=>{clearTimeout(searchTimer);searchGeneration++;searchTimer=setTimeout(searchSuppliers,250);};
  $('supplierRegistry').onchange=()=>{if(!$('supplierCardName').value && $('supplierRegistry').value)$('supplierCardName').value=$('supplierRegistry').selectedOptions[0].textContent;};
  $('supplierCardModal').addEventListener('shown.bs.modal',()=>{$('supplierCardSave').disabled=false;$('supplierCardSave').textContent='Salva scheda';$('supplierCardSave').onclick=()=>saveCard();$('supplierCardArchive').disabled=false;$('supplierCardArchive').onclick=()=>saveCard(true);});
  $('supplierCardModal').addEventListener('hide.bs.modal',event=>{if(saving)event.preventDefault();});
  $('supplierCardModal').addEventListener('hidden.bs.modal',()=>{document.body.classList.remove('supplier-card-modal-open');editing=null;clearTimeout(searchTimer);searchGeneration++;$('supplierCardSave').onclick=null;$('supplierCardArchive').onclick=null;$('supplierCardError').textContent='';});
  reload();
 });
})();

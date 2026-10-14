(() => {
 const $=id=>document.getElementById(id), node=$('supplierExternalModal');
 if(!node)return;
 const fields=SupplierCardFields.create('external');
 let groupId, key, busy=false, saved=false, searchTimer, searchGeneration=0;
 document.querySelectorAll('[data-external-order]').forEach(button=>button.onclick=event=>{
  event.stopPropagation();if(busy)return;
  groupId=button.dataset.groupId;key=crypto.randomUUID();saved=false;
  $('supplierExternalForm').reset();fields.reset();$('externalName').value='Ordine - '+button.dataset.groupName;
  $('externalSupplier').replaceChildren(new Option('Senza collegamento alla Rubrica',''));
  $('supplierExternalResult').replaceChildren();$('supplierExternalError').textContent='';$('supplierExternalSave').disabled=false;
  bootstrap.Modal.getOrCreateInstance(node).show();
 });
 node.addEventListener('hide.bs.modal',event=>{if(busy)event.preventDefault();});
 node.addEventListener('hidden.bs.modal',()=>{clearTimeout(searchTimer);searchGeneration++;});
 $('externalSupplierSearch').oninput=()=>{
  clearTimeout(searchTimer);const generation=++searchGeneration;
  searchTimer=setTimeout(async()=>{
   const selected=$('externalSupplier').selectedOptions[0];
   try{
    const response=await fetch('/registry/api/registries?kind=supplier&compact=1&q='+encodeURIComponent($('externalSupplierSearch').value),{cache:'no-store'});
    const payload=await response.json();if(!response.ok)throw Error(payload.error||'Ricerca non disponibile.');if(generation!==searchGeneration)return;
    const suppliers=payload.registries||[];
    if(selected?.value&&!suppliers.some(s=>String(s.id)===selected.value))suppliers.unshift({id:selected.value,display_name:selected.textContent});
    $('externalSupplier').replaceChildren(new Option('Senza collegamento alla Rubrica',''),...suppliers.map(s=>new Option(s.display_name,String(s.id),false,String(s.id)===selected?.value)));
   }catch(error){if(generation===searchGeneration)$('supplierExternalError').textContent=error.message;}
  },250);
 };
 $('supplierExternalForm').onsubmit=async event=>{
  event.preventDefault();if(busy||saved)return;
  busy=true;$('supplierExternalSave').disabled=true;$('supplierExternalError').textContent='';
  try{
   const body=fields.multipart({title:$('externalName').value,reference:$('externalReference').value,column_id:Number($('externalColumn').value),supplier_id:$('externalSupplier').value?Number($('externalSupplier').value):null,client_key:key});
   const response=await fetch(`/supplier-orders/groups/${groupId}/external-orders`,{method:'POST',body,cache:'no-store'});
   const payload=await response.json();if(!response.ok||!payload.ok)throw Error(payload.error||'Salvataggio non riuscito.');
   const link=document.createElement('a');link.href=payload.board_url;link.className='btn btn-info';link.textContent='Apri la nuova scheda nella bacheca';$('supplierExternalResult').replaceChildren(link);saved=true;
  }catch(error){$('supplierExternalError').textContent=error.message;}
  finally{busy=false;$('supplierExternalSave').disabled=saved;}
 };
})();

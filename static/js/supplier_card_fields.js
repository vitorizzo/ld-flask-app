window.SupplierCardFields = {
 create(prefix) {
  const $ = suffix => document.getElementById(prefix + suffix);
  let attachments = [], files = [], removed = new Set();
  const terms = () => { $('OtherWrap').hidden = $('Terms').value !== 'other'; $('Other').required = $('Terms').value === 'other'; $('Terms').required = $('Cash').checked; };
  $('Terms').onchange = terms; $('Cash').onchange = terms;
  function render() {
   $('Attachments').replaceChildren();
   for (const item of [...attachments.filter(a => !removed.has(a.id)), ...files.map((f, index) => ({filename:f.name,size:f.size,index}))]) {
    const row = document.createElement('div'); row.className = 'supplier-card-attachment-row';
    const label = document.createElement(item.url ? 'a' : 'span'); label.className = item.url ? 'supplier-card-attachment-link' : 'supplier-card-attachment-name'; label.textContent = `${item.filename} (${(item.size/1024/1024).toFixed(2)} MB)`;
    if (item.url) { label.href=item.url; label.download=item.filename; label.setAttribute('aria-label','Scarica allegato '+item.filename); }
    const button = document.createElement('button'); button.type='button'; button.className='btn btn-sm btn-outline-danger'; button.textContent='Rimuovi'; button.setAttribute('aria-label', 'Rimuovi '+item.filename);
    button.onclick=()=>{if(item.id)removed.add(item.id);else files.splice(item.index,1);render();};
    row.append(label,button); $('Attachments').append(row);
   }
  }
  $('Files').onchange=()=>{files.push(...$('Files').files);$('Files').value='';render();};
  return {
   reset(card={}) {
    for(const [suffix,key] of Object.entries({OrderText:'order_text',TransmissionNotes:'transmission_notes',Terms:'payment_terms',Other:'payment_terms_other',PaymentDate:'payment_date'}))$(suffix).value=card?.[key]||'';
    $('Cash').checked=Boolean(card?.cash_on_delivery);attachments=card?.attachments||[]; files=[]; removed=new Set();$('Files').value='';terms();render();
   },
   multipart(payload) {
    if($('Cash').checked&&!$('Terms').value)throw Error('Con contrassegno seleziona il termine di pagamento.');
    if($('Terms').value==='other'&&!$('Other').value.trim())throw Error('Specifica il termine di pagamento Altro.');
    const retained=attachments.filter(a=>!removed.has(a.id));
    if(retained.length+files.length>10)throw Error('Massimo 10 allegati per scheda.');
    if(files.some(f=>f.size>10*1024*1024))throw Error('Massimo 10 MB per allegato.');
    if([...retained,...files].reduce((sum,f)=>sum+f.size,0)>50*1024*1024)throw Error('Massimo 50 MB di allegati per scheda.');
    Object.assign(payload,{order_text:$('OrderText').value,transmission_notes:$('TransmissionNotes').value,cash_on_delivery:$('Cash').checked,payment_terms:$('Terms').value,payment_terms_other:$('Other').value,payment_date:$('PaymentDate').value,remove_attachment_ids:[...removed]});
    const body=new FormData();body.append('data',JSON.stringify(payload));files.forEach(f=>body.append('files',f));return body;
   }
  };
 }
};

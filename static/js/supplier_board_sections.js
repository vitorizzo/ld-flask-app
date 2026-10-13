(() => {
 'use strict';
 const $ = id => document.getElementById(id);
 const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const allowed = new Set(['P','DIV','BR','STRONG','B','EM','I','U','S','UL','OL','LI','BLOCKQUOTE','H3','H4']);
 const dropped = new Set(['SCRIPT','STYLE','IFRAME','OBJECT','SVG','MATH','TEMPLATE']);
 const colorFields = {badge_fill:'supplierBadgeFill',badge_text:'supplierBadgeText',badge_border:'supplierBadgeBorder'};
 const colorProperties = {badge_fill:'fill',badge_text:'text',badge_border:'border'};
 const badgeStyle = section => Object.entries(colorProperties).filter(([key])=>/^#[0-9a-f]{6}$/i.test(section[key]||''))
  .map(([key,property])=>`--supplier-badge-${property}:${section[key]}`).join(';');
 function clean(value) {
  const template = document.createElement('template'); template.innerHTML = String(value || '');
  const walk = parent => [...parent.childNodes].forEach(node => {
   if (node.nodeType === Node.COMMENT_NODE) {node.remove();return;}
   if (node.nodeType !== Node.ELEMENT_NODE) return;
   if (dropped.has(node.tagName)) {node.remove();return;}
   walk(node);
   if (!allowed.has(node.tagName)) node.replaceWith(...node.childNodes);
   else [...node.attributes].forEach(attribute => node.removeAttribute(attribute.name));
  });
  walk(template.content);
  return template.content.textContent.trim() ? template.innerHTML : '';
 }
 let hints = [];
 function hideHints() {hints.forEach(item=>{clearTimeout(item.timer);item.over=false;item.instance.hide();});}
 function disposeHints() {hints.forEach(item=>{clearTimeout(item.timer);item.instance.dispose();});hints=[];}
 document.addEventListener('click',event=>hints.forEach(item=>{
  const hint=document.getElementById(item.button.getAttribute('aria-describedby'));
  if(!item.button.contains(event.target)&&!hint?.contains(event.target)) {
   clearTimeout(item.timer);item.over=false;item.instance.hide();
  }
 }));
 function badges(card) {
  return (card.sections || []).filter(section=>section.text || clean(section.content_html)).map(section =>
   `<button type="button" class="supplier-section-badge" style="${badgeStyle(section)}" data-section-hint="${card.id}:${section.section_id}" aria-label="Leggi ${esc(section.name)}">${esc(section.name)}</button>`).join('');
 }
 function bindHints(cards) {
  document.querySelectorAll('[data-section-hint]').forEach(button => {
   const [cardId, sectionId] = button.dataset.sectionHint.split(':').map(Number);
   const section = cards.find(card=>card.id===cardId)?.sections?.find(item=>item.section_id===sectionId);
   if (!section) return;
   const item = {button,timer:null, over:false, instance:new bootstrap.Popover(button, {
    trigger:'manual', container:'body', placement:'top', html:true, animation:false,
    title:esc(section.name), content:`<div class="supplier-rich-text">${clean(section.content_html)}</div>`,
    customClass:'supplier-section-hint', fallbackPlacements:['top','bottom','left','right'],
   })};
   const show = () => {
    clearTimeout(item.timer);
    hints.filter(other=>other!==item).forEach(other=>{clearTimeout(other.timer);other.over=false;other.instance.hide();});
    if (!button.hasAttribute('aria-describedby')) item.instance.show();
   };
   const hideLater = () => {clearTimeout(item.timer);item.timer=setTimeout(()=>{
    if (!item.over && document.activeElement!==button) item.instance.hide();
   },200);};
   button.addEventListener('mouseenter',()=>{item.over=true;show();});
   button.addEventListener('mouseleave',()=>{item.over=false;hideLater();});
   button.addEventListener('focus',show);button.addEventListener('blur',hideLater);
   button.addEventListener('click',event=>{event.stopPropagation();show();});
   button.addEventListener('keydown',event=>{if(event.key==='Escape'){event.stopPropagation();item.instance.hide();button.blur();}});
   button.addEventListener('shown.bs.popover',()=>{
    const hint = document.getElementById(button.getAttribute('aria-describedby'));
    hint?.addEventListener('mouseenter',()=>{item.over=true;clearTimeout(item.timer);});
    hint?.addEventListener('mouseleave',()=>{item.over=false;hideLater();});
   });
   hints.push(item);
  });
 }
 function create({api, getData, reload}) {
  let texts = {}, activeSection = null, definition = null, configBusy = false, colors = {};
  const definitions = () => getData().sections || [];
  function setEditorOpen(open) {
   $('supplierCardModal').classList.toggle('supplier-section-editing',open);
   $('supplierSectionEditorPanel').hidden=!open;
   $('supplierCardSave').disabled=open;
   $('supplierCardArchive').disabled=open;
  }
  function renderCard() {
   $('supplierCardSectionButtons').innerHTML = definitions().map(section =>
    `<button type="button" class="btn btn-outline-secondary ${texts[section.id]?'has-content':''}" data-edit-section="${section.id}">${esc(section.name)}${texts[section.id]?' ✓':''}</button>`).join('') || '<p class="supplier-section-help">Nessuna sezione configurata. Puoi crearle dalla bacheca.</p>';
   $('supplierCardSectionContents').innerHTML = definitions().filter(section=>texts[section.id]).map(section=>
    `<section class="supplier-section-content"><header><h6>${esc(section.name)}</h6><button type="button" class="btn btn-outline-secondary btn-sm" data-edit-section="${section.id}">Modifica</button></header><div class="supplier-rich-text">${clean(texts[section.id])}</div></section>`).join('');
   [$('supplierCardSectionButtons'),$('supplierCardSectionContents')].forEach(parent=>parent.querySelectorAll('[data-edit-section]').forEach(button=>button.onclick=()=>openEditor(Number(button.dataset.editSection))));
  }
  function reset(card=null) {
   texts = Object.fromEntries(definitions().map(section=>[String(section.id),'']));
   (card?.sections || []).forEach(section=>{texts[section.section_id]=clean(section.content_html);});
   activeSection=null;setEditorOpen(false);$('supplierSectionEditor').innerHTML='';$('supplierSectionEditorError').textContent='';renderCard();
  }
  function focusSection(id) {
   if ($('supplierCardModal').classList.contains('show')) $('supplierCardSectionButtons').querySelector(`[data-edit-section="${id}"]`)?.focus();
  }
  function closeEditor() {
   const id=activeSection;activeSection=null;setEditorOpen(false);$('supplierSectionEditor').innerHTML='';$('supplierSectionEditorError').textContent='';
   if(id!==null)focusSection(id);
  }
  function openEditor(id) {
   const section=definitions().find(row=>row.id===id);if(!section)return;
   if(activeSection!==null && clean($('supplierSectionEditor').innerHTML)!==texts[activeSection]) {
    $('supplierSectionEditorError').textContent='Applica o annulla il testo prima di cambiare sezione.';return;
   }
   activeSection=id;$('supplierSectionEditorTitle').textContent=section.name;
   $('supplierSectionEditor').innerHTML=texts[id]||'';$('supplierSectionEditorError').textContent='';setEditorOpen(true);
   $('supplierSectionEditorPanel').scrollIntoView({block:'nearest',behavior:'smooth'});$('supplierSectionEditor').focus();
  }
  function applyText() {
   if(activeSection===null)return;
   const value=clean($('supplierSectionEditor').innerHTML);
   if(value.length>20000){$('supplierSectionEditorError').textContent='Il testo supera 20.000 caratteri.';return;}
   const id=activeSection;texts[id]=value;closeEditor();renderCard();focusSection(id);
  }
  function command(name) {$('supplierSectionEditor').focus();document.execCommand(name,false,null);}
  $('supplierSectionToolbar').querySelectorAll('[data-rich-command]').forEach(button=>{
   button.onmousedown=event=>event.preventDefault();button.onclick=()=>command(button.dataset.richCommand);
  });
  $('supplierSectionEditor').addEventListener('keydown',event=>{
   if(event.key==='Tab') {
    const node=getSelection()?.anchorNode;const element=node?.nodeType===Node.ELEMENT_NODE?node:node?.parentElement;
    if(element?.closest('li') && $('supplierSectionEditor').contains(element)){event.preventDefault();command(event.shiftKey?'outdent':'indent');}
   }
   if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();applyText();}
  });
  $('supplierSectionEditor').addEventListener('paste',event=>{
   event.preventDefault();const clipboard=event.clipboardData;
   const value=clipboard?.getData('text/html') || esc(clipboard?.getData('text/plain')||'').replace(/\r?\n/g,'<br>');
   document.execCommand('insertHTML',false,clean(value));
  });
  $('supplierSectionEditor').addEventListener('drop',event=>event.preventDefault());
  $('supplierSectionApply').onclick=applyText;$('supplierSectionCancel').onclick=closeEditor;
  $('supplierSectionClear').onclick=()=>{$('supplierSectionEditor').innerHTML='';applyText();};

  function previewColors() {
   $('supplierBadgePreview').setAttribute('style',badgeStyle(colors));
   $('supplierBadgePreview').textContent=$('supplierSectionName').value.trim()||'Anteprima badge';
  }
  function loadColors(section={}) {
   const toHex=value=>{
    if(/^#[0-9a-f]{6}$/i.test(value))return value;
    const parts=value.match(/[\d.]+/g);return parts?.length>=3?'#'+parts.slice(0,3).map(v=>Math.round(Number(v)).toString(16).padStart(2,'0')).join(''):'#4a2c2a';
   };
   colors=Object.fromEntries(Object.keys(colorFields).map(key=>[key,section[key]||null]));
   // Resolve theme colors in the browser, without freezing them in the DB.
   $('supplierBadgePreview').removeAttribute('style');
   const style=getComputedStyle($('supplierBadgePreview'));
   const defaults={badge_fill:toHex(style.backgroundColor),badge_text:toHex(style.color),badge_border:toHex(style.borderTopColor)};
   Object.entries(colorFields).forEach(([key,id])=>$(id).value=colors[key]||defaults[key]);previewColors();
  }
  Object.entries(colorFields).forEach(([key,id])=>$(id).oninput=()=>{colors[key]=$(id).value;previewColors();});
  $('supplierSectionName').addEventListener('input',previewColors);
  $('supplierBadgeTheme').onclick=()=>loadColors();
  function resetDefinition() {
   definition=null;$('supplierSectionDefinitionTitle').textContent='Nuova sezione';$('supplierSectionName').value='';
   $('supplierSectionPosition').value=String(Math.max(-1,...definitions().map(row=>row.order_index))+1);
   $('supplierSectionDefinitionSave').textContent='Crea sezione';$('supplierSectionDefinitionCancel').hidden=true;
   loadColors();
  }
  function setBusy(value) {
   configBusy=value;
   $('supplierSectionsModal').querySelectorAll('button,input').forEach(element=>element.disabled=value);
  }
  function renderDefinitions() {
   $('supplierSectionDefinitions').innerHTML=definitions().map(section=>
    `<div class="supplier-section-definition-row"><div><span class="supplier-section-badge" style="${badgeStyle(section)}">${esc(section.name)}</span><small>Posizione ${section.order_index} · ${section.card_count||0} schede con testo</small></div><div class="supplier-section-editor-actions"><button type="button" class="btn btn-outline-secondary btn-sm" data-edit-definition="${section.id}">Modifica</button><button type="button" class="btn btn-outline-danger btn-sm" data-delete-definition="${section.id}">Elimina</button></div></div>`).join('') || '<p>Nessuna sezione. Crea la prima qui sotto.</p>';
   $('supplierSectionDefinitions').querySelectorAll('[data-edit-definition]').forEach(button=>button.onclick=()=>{
    if(configBusy)return;definition=definitions().find(row=>row.id===Number(button.dataset.editDefinition));
    $('supplierSectionName').value=definition.name;$('supplierSectionPosition').value=definition.order_index;
    loadColors(definition);
    $('supplierSectionDefinitionTitle').textContent='Modifica sezione';$('supplierSectionDefinitionSave').textContent='Salva modifica';$('supplierSectionDefinitionCancel').hidden=false;
    $('supplierSectionDefinitionForm').scrollIntoView({block:'nearest',behavior:'smooth'});$('supplierSectionName').focus();
   });
   $('supplierSectionDefinitions').querySelectorAll('[data-delete-definition]').forEach(button=>button.onclick=()=>deleteDefinition(Number(button.dataset.deleteDefinition)));
  }
  async function saveDefinition(event) {
   event.preventDefault();if(configBusy)return;
   const payload={name:$('supplierSectionName').value,order_index:Number($('supplierSectionPosition').value),...colors,...(definition?{revision:definition.revision}:{})};
   setBusy(true);$('supplierSectionsError').textContent='';
   try {const result=await api('/supplier-orders/api/board/sections'+(definition?'/'+definition.id:''),{method:definition?'PUT':'POST',body:JSON.stringify(payload)});
    getData().sections=result.sections;renderDefinitions();resetDefinition();await reload();
   } catch(error){$('supplierSectionsError').textContent=error.message;}
   finally {setBusy(false);}
  }
  async function deleteDefinition(id) {
   if(configBusy)return;const section=definitions().find(row=>row.id===id);if(!section)return;
   if(!window.confirm(`Eliminare la sezione «${section.name}»? Verranno eliminati anche i relativi testi in ${section.card_count||0} schede, comprese quelle archiviate.`))return;
   setBusy(true);$('supplierSectionsError').textContent='';
   try {const result=await api('/supplier-orders/api/board/sections/'+id,{method:'DELETE',body:JSON.stringify({revision:section.revision,confirm:true,card_count:section.card_count||0})});
    getData().sections=result.sections;renderDefinitions();resetDefinition();await reload();
   } catch(error){$('supplierSectionsError').textContent=error.message;}
   finally {setBusy(false);}
  }
  async function refreshDefinitions() {
   if(configBusy)return;setBusy(true);$('supplierSectionsError').textContent='';
   try {const result=await api('/supplier-orders/api/board/sections');getData().sections=result.sections;renderDefinitions();resetDefinition();}
   catch(error){$('supplierSectionsError').textContent=error.message;}
   finally{setBusy(false);}
  }
  const modal=$('supplierSectionsModal');if(modal.parentElement!==document.body)document.body.appendChild(modal);
  modal.addEventListener('show.bs.modal',()=>{document.body.classList.add('supplier-card-modal-open');renderDefinitions();resetDefinition();$('supplierSectionsError').textContent='';});
  modal.addEventListener('shown.bs.modal',()=>{
   setBusy(configBusy);$('supplierSectionDefinitionForm').onsubmit=saveDefinition;
   $('supplierSectionDefinitionCancel').onclick=resetDefinition;$('supplierSectionsReload').onclick=refreshDefinitions;
  });
  modal.addEventListener('hide.bs.modal',event=>{if(configBusy)event.preventDefault();});
  modal.addEventListener('hidden.bs.modal',()=>{
   document.body.classList.remove('supplier-card-modal-open');definition=null;
   $('supplierSectionDefinitionForm').onsubmit=null;$('supplierSectionDefinitionCancel').onclick=null;$('supplierSectionsReload').onclick=null;$('supplierSectionsError').textContent='';
  });
  $('supplierSectionsConfigure').onclick=()=>{bootstrap.Modal.getOrCreateInstance(modal).show();refreshDefinitions();};
  return {reset, payload:()=>({...texts}), editing:()=>activeSection!==null, closeEditor};
 }
 window.SupplierBoardSections={create,clean,badges,bindHints,disposeHints,hideHints};
})();

import vm from 'node:vm';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.value='';this.disabled=false;this.textContent='';this.attrs={};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 setAttribute(k,v){this.attrs[k]=v;}
 addEventListener(name,fn,options={}){(this.listeners[name]??=[]).push({fn,once:options.once});}
 emit(name){const e={prevented:false,preventDefault(){this.prevented=true;}};const handlers=[...(this.listeners[name]||[])];this.listeners[name]=(this.listeners[name]||[]).filter(h=>!h.once);handlers.forEach(h=>h.fn(e));return e;}
 focus(){this.focused=true;}
}
const ids=Object.fromEntries(['supplierProductSettingsModal','supplierSettingsRows','supplierSettingsStatus','supplierSettingsGroupName','supplierProductSettingsOpen'].map(id=>[id,new Node()]));
const parent=new Node();let parentShows=0,settingsShows=0,confirmResult=false,pendingResolve,fail=false;const requests=[];
const modal={show(){settingsShows++;ids.supplierProductSettingsModal.emit('shown.bs.modal');},hide(){const e=ids.supplierProductSettingsModal.emit('hide.bs.modal');if(!e.prevented)ids.supplierProductSettingsModal.emit('hidden.bs.modal');return e;}};
const parentModal={show(){parentShows++;},hide(){parent.emit('hidden.bs.modal');}};
const context={document:{getElementById:id=>ids[id],createElement:tag=>new Node(tag)},window:{confirm:()=>confirmResult},modals:new Map([['#supplierProductSettingsModal',modal]]),managerModalNode:parent,managerModal:parentModal,managerStatus:new Node(),currentGroup:{id:4,name:'Fornitore Test'},subgroupBusy:false,sortItems:items=>items,groupItems:[{root:'A',cod_art:'A1',description:'Acqua <script>',supplier_code:'FOR-A',order_description:''},{root:'A',cod_art:'A2',description:'Acqua variante'},{root:'B',cod_art:'B',description:'Bicchieri',supplier_code:'',order_description:'PDF B'}],subgroupRequest:async(path,method,data)=>{requests.push({path,method,data});if(pendingResolve)await pendingResolve;if(fail){context.managerStatus.textContent='Errore rete';return false;}context.groupItems.forEach(r=>{if(r.root===data.matrix_code){r.supplier_code=data.supplier_code.trim();r.order_description=data.order_description.trim();}});return true;}};
vm.createContext(context);const source=readFileSync('static/js/supplier_orders.js','utf8');
vm.runInContext(source.slice(source.indexOf('  const settingsNode='),source.indexOf('  function renderManager()')),context);
const editors=()=>vm.runInContext('settingsEditors',context);
ids.supplierProductSettingsOpen.onclick();assert.equal(settingsShows,1);assert.equal(ids.supplierSettingsRows.children.length,2);assert.equal(editors()[0].code.value,'FOR-A');assert.equal(editors()[1].description.value,'PDF B');
assert.equal(ids.supplierSettingsRows.children[0].children[0].children[0].textContent,'Acqua <script>');
editors()[1].code.value='NON SALVATO';editors()[0].code.value='';editors()[0].description.value='  Acqua PDF  ';await editors()[0].save.onclick();
assert.equal(requests[0].data.supplier_code,'');assert.equal(requests[0].data.matrix_code,'A');assert.equal(editors()[0].description.value,'Acqua PDF');assert.equal(editors()[0].status.textContent,'Salvato.');assert.equal(editors()[1].code.value,'NON SALVATO');
assert.equal(modal.hide().prevented,true);assert.equal(parentShows,0);
fail=true;await editors()[1].save.onclick();assert.equal(editors()[1].status.textContent,'Non salvato.');assert.equal(ids.supplierSettingsStatus.textContent,'Errore rete');assert.equal(editors()[1].save.disabled,false);
let release;pendingResolve=new Promise(resolve=>release=resolve);const saving=editors()[1].save.onclick();assert.equal(modal.hide().prevented,true);release();await saving;pendingResolve=null;
confirmResult=true;modal.hide();assert.equal(parentShows,1);assert.equal(editors().length,0);
ids.supplierProductSettingsOpen.onclick();assert.equal(settingsShows,2);assert.equal(editors()[0].description.value,'Acqua PDF');assert.equal(editors()[1].code.value,'');
modal.hide();context.groupItems=[];ids.supplierProductSettingsOpen.onclick();assert.equal(editors().length,0);assert.equal(ids.supplierSettingsRows.children[0].children[0].textContent,'Nessun prodotto associato al gruppo.');
assert.ok(source.includes('managerDirty && !settingsTransition'),'modal handoff must not reload the page');
console.log('PASS: product settings table, shared variants, optional code, per-row save, unsaved preservation, errors and modal reopen');

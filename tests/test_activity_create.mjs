import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';

class Element {
 constructor(){this.value='';this.disabled=false;this.checked=false;this.textContent='';this.dataset={};this.handlers={};this.nodes=[];this.files=[];}
 set innerHTML(value){this.html=value;this.nodes=[...value.matchAll(/data-(role|user)="(\d+)"/g)].map(([,kind,id])=>{const n=new Element();n.dataset[kind]=id;return n;});}
 get innerHTML(){return this.html||'';}
 addEventListener(type,handler){(this.handlers[type]||=[]).push(handler);}
 get selectedOptions(){return [{dataset:{}}];}
 fire(type){for(const fn of this.handlers[type]||[])fn({preventDefault(){}});}
 querySelectorAll(selector){if(selector.includes('[data-user]'))return this.nodes.filter(n=>n.dataset.user);if(selector.includes('[data-role]'))return this.nodes.filter(n=>n.dataset.role&&(!selector.includes(':checked')||n.checked));return [];}
 focus(){}
}
const ids=['activityCreateTitle','activityCreateContext','activitySharedFiles','activityCreateModal','activityNew','activityCreateSave','activityNewTitle','activityNewDescription','activityNewFiles','activityCreateError'];
for(const prefix of ['activity','activityResult'])for(const suffix of ['SelectedUsers','NewUsers','UsersHint','NewRoles','UserRole','UserSearch','MinWeight','UsersSelect'])ids.push(prefix+suffix);
const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
const $=id=>elements[id],modal=$('activityCreateModal');
modal.querySelectorAll=()=>Object.values(elements);
const calls=[],roles=[{id:1,name:'Staff',weight:30},{id:2,name:'Ufficio',weight:40}];let fail=true,created=0;
const api=async(url,options={})=>{
 if(url.startsWith('/activities/api/assignees'))return {roles,users:url.includes('role_id=1')?[{id:2,name:'Mario'}]:[{id:2,name:'Mario'},{id:6,name:'Anna'}],total:2};
 assert.ok(options.body instanceof FormData||options.method==='PUT');const payload=typeof options.body==='string'?JSON.parse(options.body):JSON.parse(options.body.get('data'));calls.push({payload,method:options.method,files:typeof options.body==='string'?[]:options.body.getAll('files')});
 if(fail){fail=false;throw Error('Rete non disponibile');}return {ok:true};
};
const bootstrap={Modal:{getOrCreateInstance(){return {show(){modal.fire('shown.bs.modal');},hide(){modal.fire('hidden.bs.modal');}};}}};
const context={window:{},document:{getElementById:$},bootstrap,crypto:webcrypto,FormData,URLSearchParams,setTimeout,clearTimeout,console};
vm.runInNewContext(readFileSync('static/js/activity_create.js','utf8'),context);
const composer=context.window.ActivityCreate.init({api,onCreated:async()=>created++});
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
$('activityNew').onclick();await tick();assert.equal($('activityCreateSave').disabled,false);
$('activityNewTitle').value='Inventario';$('activityMinWeight').value='30';
await $('activityCreateSave').onclick();assert.equal(calls.length,0,'result recipients required separately');
$('activityResultMinWeight').value='40';
$('activityUserRole').value='1';$('activityUserRole').onchange();await tick();$('activityUsersSelect').onclick();
$('activityUserRole').value='';$('activityUserRole').onchange();await tick();
$('activityResultUsersSelect').onclick();
$('activityNewFiles').files=[new Blob(['image contents'],{type:'image/png'})];
await $('activityCreateSave').onclick();assert.equal(calls.length,1);assert.match($('activityCreateError').textContent,/Rete/);assert.equal(created,0);
assert.deepEqual(calls[0].payload.user_ids,[2],'selection survives user filter');
assert.deepEqual(calls[0].payload.result_recipients.user_ids,[2,6],'result selection independent');
assert.equal(calls[0].payload.result_recipients.target_min_weight,40);assert.equal(calls[0].files.length,1);
await $('activityCreateSave').onclick();assert.equal(created,1);assert.equal(calls[0].payload.client_key,calls[1].payload.client_key);assert.equal($('activityCreateSave').onclick,null,'hidden cleans save handler');
$('activityNew').onclick();await tick();assert.equal($('activityCreateSave').disabled,false);assert.equal($('activityMinWeight').value,'');assert.equal($('activityResultMinWeight').value,'');
await $('activityCreateSave').onclick();assert.equal(calls.length,2,'new creation clears targets');
console.log('PASS: independent result selectors, required recipients, filter preservation, multipart attachments, error retry, stable key and modal reopen');

const existing={id:12,title:'Reso concluso',description:'Istruzioni',revision:4,role_ids:[2],users:[{id:6,name:'Anna'}],target_min_weight:40,result_recipients:{role_ids:[1],users:[{id:2,name:'Mario'}],target_min_weight:30}};
composer.open({row:existing});await tick();assert.equal($('activityNewTitle').value,'Reso concluso');assert.equal($('activityMinWeight').value,'40');
assert.equal($('activityNewRoles').nodes.find(n=>n.dataset.role==='2').checked,true);
$('activityNewTitle').value='Reso modificato';await $('activityCreateSave').onclick();assert.equal(calls.at(-1).method,'PUT');assert.equal(calls.at(-1).payload.revision,4);assert.deepEqual(calls.at(-1).payload.user_ids,[6]);
composer.open({parent:{id:12,title:'Reso',revision:7,attachments:[{id:3,filename:'conteggio.pdf'}],photos:[]}});await tick();
$('activityNewTitle').value='Reconta';$('activityMinWeight').value='30';$('activityResultMinWeight').value='40';await $('activityCreateSave').onclick();
assert.equal(calls.at(-1).payload.parent_id,12);assert.equal(calls.at(-1).payload.parent_revision,7);assert.equal(calls.at(-1).method,'POST');
console.log('PASS: edit prefill, exact role/user preservation, revision and subactivity creation context');

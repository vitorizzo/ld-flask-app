import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source = fs.readFileSync('static/js/agenda.js', 'utf8');
const part = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const element = () => ({innerHTML:'', value:'', disabled:false, appendChild(){}, querySelectorAll(){return []}});
const pending = [];
const ctx = {
  currentDay:'2026-10-13', depositLoading:false, depositReady:false, depositLoadGeneration:0,
  depositBankSelect:element(), depositTypeSelect:element(), depositChecksTableBody:element(),
  depositTableBody:element(), depositAddBtn:element(), console,
  document:{createElement:element}, alert:()=>assert.fail('Unexpected alert'),
  escapeHtml:String, formatDateIT:String, formatEuro2:String,
  updateDepositTotal(){}, updateDepositCashUi(){}, configureDepositTabOrder(){},
  resetDepositForm(){ctx.depositTypeSelect.value='versamento_incasso'},
  depositModal:{show(){ctx.shown=(ctx.shown||0)+1}},
  fetch(url){return new Promise(resolve=>pending.push({url, resolve}))},
};
vm.createContext(ctx);
vm.runInContext([
  part('  async function fetchBanksRaw()', '  async function loadBanks('),
  part('  async function loadDepositBanks(', '  function updateMultiRowFields('),
  part('  async function loadAvailableDepositChecks(', '  function depositOrderedFocusTargets('),
].join('\n'),ctx);
const respond = (requests, failed=false) => requests.forEach(({url,resolve})=>resolve({json:async()=>
  failed ? {ok:false,error:'test failure'} : url.endsWith('/banks') ? {ok:true,banks:[{id:1,name:'Bank',is_default:true}]} :
  {ok:true,incasso:[],intermedio:[],deposits:[]}}));
const opening = ctx.openDepositModal();
assert.equal(ctx.shown,1, 'Modal must show while requests are still pending');
assert.equal(pending.length,3, 'Requests must start concurrently');
assert.equal(ctx.depositAddBtn.disabled,true);
await ctx.openDepositModal();
assert.equal(pending.length,3, 'Double click must not duplicate requests');
const old = pending.splice(0);
// Same invalidation as hidden.bs.modal, followed by opening another day.
ctx.depositLoadGeneration++;ctx.depositLoading=false;ctx.depositReady=false;
ctx.currentDay='2026-10-14';
const reopening=ctx.openDepositModal();
respond(old);await opening;
assert.equal(ctx.depositAddBtn.disabled,true, 'Old response cannot enable a new form');
assert.match(ctx.depositChecksTableBody.innerHTML,/Caricamento/);
respond(pending.splice(0));await reopening;
assert.equal(ctx.depositAddBtn.disabled,false);
assert.equal(ctx.depositReady,true);
const failed=ctx.openDepositModal();respond(pending.splice(0),true);await failed;
assert.equal(ctx.depositAddBtn.disabled,true, 'Failure must prevent incomplete submission');
assert.equal(ctx.depositReady,false);
const retry=ctx.openDepositModal();respond(pending.splice(0));await retry;
assert.equal(ctx.depositAddBtn.disabled,false, 'Reopening must recover after failure');
console.log('PASS: immediate modal, parallel requests, duplicate click, stale response, failure and retry');

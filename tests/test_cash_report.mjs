import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source = fs.readFileSync('static/js/agenda.js', 'utf8');
const start = source.indexOf('function reportDayLabel(');
const functions = source.slice(source.indexOf('function reportMoney('), source.indexOf('function movementMethodLabel(')) + source.slice(start, source.indexOf('function buildCompleteDayReportHtml(', start));
const context = vm.createContext({ currentDay: '2026-10-08', priVaultUnlocked: false, escapeHtml: value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'), formatDateTimeIT: value => value });
vm.runInContext(functions, context);
let count = 0;
for (const full of [false, true]) {
  context.priVaultUnlocked = full;
  for (const intermediate of [0, 300, 450]) {
    const payload = { preview: { totals: { versabile_giornata: 1000, versabile_residuo: 1000-intermediate, totale_versato_intermedio: intermediate } }, ownerTakes: { owner_takes: [{take_type:'parziale', cash_amount:100}, {take_type:'serale', cash_amount:900-intermediate}] } };
    const html = context.buildReportBodyHtml(payload);
    const money = context.signedReportMoney;
    assert.ok(html.includes(`Totale consegnato (totale prelevato ${money(1000)})`));
    assert.ok(html.includes(`Totale versabile (totale ${money(1000)})</td><td>${money(1000-intermediate)}`));
    assert.ok(html.includes(`Totale consegnato (totale prelevato ${money(1000)})</td><td>${money(900-intermediate)}`));
    count++;
  }
  const legacy = {preview:{totals:{versabile_giornata:1000}},deposits:{deposits:[{deposit_type:'versamento_intermedio',cash_amount:200,check_amount:100},{deposit_type:'versamento_incasso',cash_amount:500}]},ownerTakes:{owner_takes:[{take_type:'serale',cash_amount:700}]}};
  const html = context.buildReportBodyHtml(legacy);
  assert.ok(html.includes(`Totale versabile (totale ${context.signedReportMoney(1000)})</td><td>${context.signedReportMoney(700)}`));
  assert.ok(html.includes(`Totale consegnato (totale prelevato ${context.signedReportMoney(1000)})`));
  count++;
}
console.log(`${count} report cases passed`);

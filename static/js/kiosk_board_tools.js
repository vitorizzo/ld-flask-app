/* Configurazione DB degli stati e selezione multipla della bacheca. */
(() => {
  const $ = id => document.getElementById(id);
  const html = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let hooks, selecting = false, busy = false, rows = [], selected = new Set(), snapshot = [];
  let configRequest = 0, configSaving = false;
  let deletedCodes = [];
  const modal = id => bootstrap.Modal.getOrCreateInstance($(id));

  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }
  function visibleCards() {
    return Array.from(document.querySelectorAll('.order-card')).filter(card => card.getClientRects().length && !card.closest('.is-mobile-status-hidden'));
  }
  function updateSelection() {
    $('kioskBulkBar').hidden = !selecting;
    $('btn-select-orders').setAttribute('aria-pressed', String(selecting));
    $('btn-select-orders').querySelector('.tools-label').textContent = selecting ? ' Fine' : ' Seleziona';
    $('btn-select-orders').setAttribute('aria-label', selecting ? 'Termina selezione' : 'Seleziona schede');
    $('kioskSelectionCount').textContent = `${selected.size} ordini selezionati`;
    $('bulkOpen').disabled = !selected.size || busy;
    document.querySelectorAll('.order-card').forEach(card => {
      const ids = JSON.parse(card.dataset.selectionIds || '[]');
      const checkbox = card.querySelector('[data-select-card]');
      const count = ids.filter(id => selected.has(id)).length;
      card.classList.toggle('is-selected', count > 0);
      if (checkbox) { checkbox.checked = count === ids.length; checkbox.indeterminate = count > 0 && count < ids.length; checkbox.disabled = busy; }
      const label = card.querySelector('.kiosk-card-select');
      if (label) label.hidden = !selecting;
    });
  }
  function attachCard(card, vm) {
    const ids = [...new Set(vm.orders.map(order => Number(order.id)))];
    card.dataset.selectionIds = JSON.stringify(ids);
    const label = document.createElement('label');
    label.className = 'kiosk-card-select';
    label.hidden = !selecting;
    label.innerHTML = `<input type="checkbox" data-select-card aria-label="Seleziona ${ids.length} ordini"><span>Seleziona${ids.length > 1 ? ` (${ids.length} ordini)` : ''}</span>`;
    label.addEventListener('click', event => event.stopPropagation());
    label.querySelector('input').addEventListener('change', event => {
      ids.forEach(id => event.target.checked ? selected.add(id) : selected.delete(id));
      updateSelection();
    });
    card.prepend(label);
    card.addEventListener('click', event => {
      if (!selecting || event.target.closest('button,a,input,select,textarea,label')) return;
      event.stopImmediatePropagation();
      if (busy) return;
      const all = ids.every(id => selected.has(id));
      ids.forEach(id => all ? selected.delete(id) : selected.add(id));
      updateSelection();
    }, true);
  }
  function syncSelection(cards) {
    const live = new Set(cards.flatMap(card => card.orders.map(order => Number(order.id))));
    selected = new Set([...selected].filter(id => live.has(id)));
    updateSelection();
  }
  function renderConfig() {
    $('statusConfigRows').innerHTML = rows.map((row, index) => `<section class="status-config-row" data-row="${index}">
      <div class="status-config-fields">
        <label>Nome colonna<input class="form-control" data-field="label" maxlength="64" value="${html(row.label)}"></label>
        <label>Codice<input class="form-control" data-field="code" maxlength="30" value="${html(row.code)}" ${row.existing ? 'readonly' : ''}></label>
        <label>Reaction Slack<input class="form-control" data-field="slack_reaction" maxlength="66" placeholder="truck" value="${html(row.slack_reaction)}"></label>
      </div>
      <div class="status-config-checks"><label><input type="checkbox" data-field="is_visible" ${row.is_visible ? 'checked' : ''}> Colonna visibile</label><label><input type="checkbox" data-field="is_terminal" ${row.is_terminal ? 'checked' : ''}> Stato finale</label><span class="small">${Number(row.order_count || 0)} ordini</span></div>
      <div class="status-config-actions"><button type="button" class="btn btn-sm btn-outline-secondary" data-direction="-1" ${index === 0 ? 'disabled' : ''}>Sposta su</button><button type="button" class="btn btn-sm btn-outline-secondary" data-direction="1" ${index === rows.length-1 ? 'disabled' : ''}>Sposta giu'</button><button type="button" class="btn btn-sm btn-outline-danger" data-remove ${row.is_protected || row.order_count > 0 ? 'disabled' : ''}>Elimina colonna</button></div>
      ${row.is_protected ? '<p class="small mb-0 mt-2">Stato usato dai flussi dell\'app: non eliminabile.</p>' : row.order_count > 0 ? '<p class="small mb-0 mt-2">Sposta gli ordini con il cambio stato massivo, poi elimina la colonna.</p>' : ''}
    </section>`).join('');
    $('statusConfigRows').querySelectorAll('[data-field]').forEach(input => input.addEventListener('input', () => {
      const row = rows[Number(input.closest('[data-row]').dataset.row)];
      row[input.dataset.field] = input.type === 'checkbox' ? input.checked : input.value;
    }));
    $('statusConfigRows').querySelectorAll('[data-direction],[data-remove]').forEach(button => button.addEventListener('click', () => {
      const index = Number(button.closest('[data-row]').dataset.row);
      if (button.hasAttribute('data-remove')) {
        if (rows[index].existing) deletedCodes.push(rows[index].code);
        rows.splice(index, 1);
        $('statusConfigError').textContent = 'Colonna rimossa dalla configurazione. Premi Salva per confermare, oppure Annulla per ripristinarla.';
      }
      else { const target = index + Number(button.dataset.direction); [rows[index], rows[target]] = [rows[target], rows[index]]; }
      renderConfig();
    }));
  }
  async function openConfig() {
    const generation = ++configRequest;
    rows = [];
    deletedCodes = [];
    $('statusConfigRows').textContent = 'Caricamento...';
    $('statusConfigError').textContent = '';
    modal('statusConfigModal').show();
    $('statusConfigSave').disabled = true;
    $('statusConfigAdd').disabled = true;
    try {
      const data = await jsonRequest('/kiosk/api/status-config');
      if (generation !== configRequest) return;
      rows = data.statuses.map(row => ({...row, existing: true}));
      renderConfig();
      $('statusConfigSave').disabled = false;
      $('statusConfigAdd').disabled = false;
    } catch (error) { if (generation === configRequest) $('statusConfigError').textContent = error.message; }
  }
  async function saveConfig() {
    if (configSaving || !rows.length) return;
    configSaving = true;
    $('statusConfigSave').disabled = true;
    $('statusConfigSave').textContent = 'Salvataggio...';
    $('statusConfigError').textContent = '';
    $('statusConfigRows').querySelectorAll('input,button').forEach(input => input.disabled = true);
    $('statusConfigAdd').disabled = true;
    try {
      await jsonRequest('/kiosk/api/status-config', {method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify({statuses: rows, deleted_codes: deletedCodes})});
      await hooks.reloadStatuses();
      await hooks.reloadOrders();
      configSaving = false;
      modal('statusConfigModal').hide();
    } catch (error) { $('statusConfigError').textContent = error.message; }
    finally {
      configSaving = false;
      $('statusConfigSave').disabled = false;
      $('statusConfigSave').textContent = 'Salva configurazione';
      $('statusConfigAdd').disabled = false;
      renderConfig();
    }
  }
  function openBulk() {
    snapshot = [...selected];
    if (!snapshot.length) return;
    $('bulkOrdersSummary').textContent = `Applicherai lo stesso stato a ${snapshot.length} ordini. Le schede raggruppate includono tutti gli ordini contenuti. La selezione include anche eventuali schede nascoste dai filtri.`;
    $('bulkOrdersStatus').innerHTML = '<option value="">Seleziona uno stato</option>' + kioskState.statusMeta.map(row => `<option value="${html(row.code)}">${html(row.label)}</option>`).join('');
    $('bulkOrdersResults').textContent = '';
    modal('bulkOrdersModal').show();
  }
  async function applyBulk() {
    const status = $('bulkOrdersStatus').value;
    if (busy || !snapshot.length) return;
    if (!status) { $('bulkOrdersResults').textContent = 'Seleziona lo stato di destinazione.'; return; }
    busy = true;
    $('bulkOrdersApply').disabled = true;
    $('bulkOrdersStatus').disabled = true;
    $('bulkOrdersModal').querySelectorAll('[data-bs-dismiss]').forEach(button => button.disabled = true);
    $('btn-select-orders').disabled = true;
    $('bulkClear').disabled = true;
    $('bulkSelectVisible').disabled = true;
    updateSelection();
    const failures = [], warnings = [];
    let done = 0;
    for (const id of snapshot) {
      $('bulkOrdersResults').textContent = `Elaborazione ${done + failures.length + 1} di ${snapshot.length}...`;
      try {
        const data = await hooks.setStatus(id, status);
        selected.delete(id);
        done++;
        if (data.warning) warnings.push(`#${id}: ${data.warning}`);
      } catch (error) { failures.push({id, error: error.message}); }
    }
    snapshot = failures.map(item => item.id);
    try { await hooks.reloadOrders(); } finally {
      busy = false;
      $('bulkOrdersStatus').disabled = false;
      $('bulkOrdersModal').querySelectorAll('[data-bs-dismiss]').forEach(button => button.disabled = false);
      $('btn-select-orders').disabled = false;
      $('bulkClear').disabled = false;
      $('bulkSelectVisible').disabled = false;
      $('bulkOrdersApply').disabled = !snapshot.length;
      $('bulkOrdersApply').textContent = snapshot.length ? 'Riprova gli ordini non aggiornati' : 'Operazione completata';
      $('bulkOrdersResults').textContent = [`${done} ordini aggiornati; ${failures.length} non aggiornati.`, ...failures.map(item => `#${item.id}: ${item.error}`), ...warnings].join('\n');
      updateSelection();
    }
  }
  function init(callbacks) {
    hooks = callbacks;
    $('btn-status-config').addEventListener('click', openConfig);
    $('btn-select-orders').addEventListener('click', () => { selecting = !selecting; if (!selecting) selected.clear(); updateSelection(); });
    $('bulkClear').addEventListener('click', () => { selected.clear(); updateSelection(); });
    $('bulkSelectVisible').addEventListener('click', () => { visibleCards().forEach(card => JSON.parse(card.dataset.selectionIds).forEach(id => selected.add(id))); updateSelection(); });
    $('bulkOpen').addEventListener('click', openBulk);
    $('statusConfigAdd').addEventListener('click', () => {
      rows.push({code:'',label:'',slack_reaction:'',is_visible:true,is_terminal:false}); renderConfig();
      const input = $('statusConfigRows').lastElementChild.querySelector('[data-field="label"]');
      input.scrollIntoView({block:'center'}); input.focus();
    });
    $('statusConfigModal').addEventListener('shown.bs.modal', () => { $('statusConfigSave').textContent = 'Salva configurazione'; $('statusConfigSave').disabled = !rows.length; $('statusConfigSave').onclick = saveConfig; });
    $('statusConfigModal').addEventListener('hide.bs.modal', event => { if (configSaving) event.preventDefault(); });
    $('statusConfigModal').addEventListener('hidden.bs.modal', () => { configRequest++; rows = []; deletedCodes = []; $('statusConfigSave').onclick = null; $('statusConfigError').textContent = ''; });
    $('bulkOrdersModal').addEventListener('shown.bs.modal', () => { $('bulkOrdersApply').disabled = false; $('bulkOrdersApply').textContent = 'Applica agli ordini selezionati'; $('bulkOrdersApply').onclick = applyBulk; });
    $('bulkOrdersModal').addEventListener('hide.bs.modal', event => { if (busy) event.preventDefault(); });
    $('bulkOrdersModal').addEventListener('hidden.bs.modal', () => { snapshot = []; $('bulkOrdersApply').onclick = null; $('bulkOrdersResults').textContent = ''; });
  }
  window.KioskBoardTools = {init, attachCard, syncSelection, isSelecting: () => selecting};
})();

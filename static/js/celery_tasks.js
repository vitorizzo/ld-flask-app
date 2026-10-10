(() => {
  'use strict';
  const root = document.getElementById('celerySettings');
  if (!root) return;
  const rows = document.getElementById('celeryTaskRows');
  const feedback = document.getElementById('celeryFeedback');
  const beatLabel = document.getElementById('celeryBeatStatus');
  const showDeleted = document.getElementById('celeryShowDeleted');
  const modalNode = document.getElementById('celeryConfirmModal');
  document.body.appendChild(modalNode);
  const confirmButton = document.getElementById('celeryConfirmButton');
  const confirmError = document.getElementById('celeryConfirmError');
  let state = null, busy = false, pending = null;
  const cronFields = [['minute', 'Minuti'], ['hour', 'Ore'], ['day_of_week', 'Giorni settimana'], ['day_of_month', 'Giorni mese'], ['month_of_year', 'Mesi']];
  const say = (message, error = false) => { feedback.textContent = message; feedback.dataset.error = String(error); };
  const setBusy = value => {
    busy = value;
    root.querySelectorAll('button').forEach(button => { button.disabled = value || button.dataset.locked === 'true'; });
    root.querySelectorAll('input, select').forEach(input => { input.disabled = value || input.dataset.locked === 'true'; });
    modalNode.querySelectorAll('button').forEach(button => { button.disabled = value; });
  };
  async function request(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', headers: {'Content-Type': 'application/json'}, signal: controller.signal, ...options});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(data.error || 'Richiesta non riuscita. Verifica la sessione e riprova.');
      if (!Array.isArray(data.tasks) || !Number.isInteger(data.revision)) throw Error('Risposta non valida. Riprova.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw Error('Risposta non ricevuta. Aggiorna per verificare se la modifica è stata salvata.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function beatStatus(data) {
    if (!data.beat) beatLabel.textContent = 'In attesa di Celery Beat. Le modifiche richiedono lo scheduler aggiornato e attivo.';
    else if (data.beat.error) beatLabel.textContent = 'Celery Beat non riesce a leggere le configurazioni: gli avvii periodici sono sospesi fino al recupero.';
    else if (data.beat.revision === data.revision) beatLabel.textContent = `Configurazione applicata da Celery Beat · revisione ${data.revision}`;
    else beatLabel.textContent = `Configurazione salvata · revisione ${data.revision}. In attesa di applicazione da Celery Beat (circa 5 secondi).`;
  }
  function fillRow(task) {
    const tr = document.createElement('tr'); tr.dataset.id = task.id;
    tr.innerHTML = '<td data-label="Nome"><strong class="celery-task-name"></strong><small class="celery-task-code"></small></td><td data-label="Tipologia" class="celery-type"></td><td data-label="Frequenza"><div class="celery-frequency"><label>Modalità<select data-field="kind"><option value="cron">Calendario</option><option value="interval">Intervallo</option></select></label><div class="celery-interval"><label>Ogni<input type="number" min="1" step="1" data-field="amount"></label><label>Unità<select data-field="unit"><option value="60">Minuti</option><option value="3600">Ore</option><option value="86400">Giorni</option></select></label></div><div class="celery-cron"></div><small class="celery-cron-help">Calendario: * tutti; */5 ogni 5; 6-22 fascia; 0,30 elenco. Domenica=0, lunedì=1.</small><button class="btn" type="button" data-action="frequency">Salva frequenza</button></div></td><td data-label="Stato"><span class="celery-state"></span></td><td data-label="Azioni"><div class="celery-row-actions"></div></td>';
    tr.querySelector('.celery-task-name').textContent = task.name;
    tr.querySelector('.celery-task-code').textContent = task.task;
    tr.querySelector('.celery-type').textContent = task.type;
    const editor = tr.querySelector('.celery-frequency');
    const details = document.createElement('details'); details.className = 'celery-frequency-editor';
    const toggle = document.createElement('summary'); toggle.textContent = 'Modifica frequenza';
    editor.before(details); details.append(toggle, editor);
    const summary = document.createElement('span'); summary.className = 'celery-frequency-summary';
    summary.textContent = frequencyText(task.frequency); details.before(summary);
    const cron = tr.querySelector('.celery-cron');
    cronFields.forEach(([field, label]) => {
      const wrap = document.createElement('label'); wrap.append(document.createTextNode(label));
      const input = document.createElement('input'); input.type = 'text'; input.dataset.field = field; input.maxLength = 160;
      input.value = task.frequency[field] || '*'; wrap.append(input); cron.append(wrap);
    });
    const frequency = task.frequency;
    tr.querySelector('[data-field=kind]').value = frequency.kind;
    let unit = 60, amount = 5;
    if (frequency.kind === 'interval') {
      unit = frequency.seconds % 86400 === 0 ? 86400 : frequency.seconds % 3600 === 0 ? 3600 : 60;
      amount = frequency.seconds / unit;
    }
    tr.querySelector('[data-field=unit]').value = String(unit);
    tr.querySelector('[data-field=amount]').value = String(amount);
    tr.querySelector('[data-field=kind]').addEventListener('change', () => frequencyVisibility(tr));
    updateState(tr, task); frequencyVisibility(tr);
    return tr;
  }
  function frequencyText(frequency) {
    if (frequency.kind === 'interval') {
      const seconds = frequency.seconds;
      const unit = seconds % 86400 === 0 ? [86400, 'giorni'] : seconds % 3600 === 0 ? [3600, 'ore'] : seconds % 60 === 0 ? [60, 'minuti'] : [1, 'secondi'];
      return `Ogni ${seconds / unit[0]} ${unit[1]}`;
    }
    let text = frequency.minute === '*' ? 'Ogni minuto' : `Minuti ${frequency.minute}`;
    if (/^\*\/\d+$/.test(frequency.minute)) text = `Ogni ${frequency.minute.slice(2)} minuti`;
    const minutes = frequency.minute.split(',').map(Number);
    if (minutes.length > 1 && minutes.every((value, index) => Number.isInteger(value) && (index === 0 || value - minutes[index - 1] === minutes[1] - minutes[0])) && minutes[minutes.length - 1] + minutes[1] - minutes[0] === 60 + minutes[0]) {
      text = `Ogni ${minutes[1] - minutes[0]} minuti` + (minutes[0] ? ` (dal minuto ${minutes[0]})` : '');
    }
    if (/^\d+$/.test(frequency.minute) && /^\d+$/.test(frequency.hour)) text = `Alle ${frequency.hour.padStart(2, '0')}:${frequency.minute.padStart(2, '0')}`;
    else if (frequency.hour !== '*') text += ` · ore ${frequency.hour}`;
    if (frequency.day_of_week !== '*') text += ` · settimana ${frequency.day_of_week}`;
    if (frequency.day_of_month !== '*') text += ` · giorni ${frequency.day_of_month}`;
    if (frequency.month_of_year !== '*') text += ` · mesi ${frequency.month_of_year}`;
    return text;
  }
  function frequencyVisibility(tr) {
    const cron = tr.querySelector('[data-field=kind]').value === 'cron';
    tr.querySelector('.celery-cron').hidden = !cron;
    tr.querySelector('.celery-cron-help').hidden = !cron;
    tr.querySelector('.celery-interval').hidden = cron;
  }
  function updateState(tr, task) {
    tr.hidden = task.deleted && !showDeleted.checked;
    tr.querySelector('.celery-state').textContent = task.deleted ? 'Eliminata' : task.enabled ? 'Attiva' : 'In pausa';
    tr.querySelectorAll('.celery-frequency input, .celery-frequency select, .celery-frequency button').forEach(el => {
      el.disabled = task.deleted || busy; el.dataset.locked = String(task.deleted);
    });
    const actions = tr.querySelector('.celery-row-actions'); actions.replaceChildren();
    const buttons = task.deleted ? [['restore', 'Ripristina in pausa', 'fa-rotate-left']] : [[task.enabled ? 'pause' : 'play', task.enabled ? 'Pausa' : 'Play', task.enabled ? 'fa-pause' : 'fa-play'], ['delete', 'Elimina', 'fa-trash']];
    buttons.forEach(([action, text, icon]) => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'btn'; button.dataset.action = action;
      const glyph = document.createElement('i'); glyph.className = `fa-solid ${icon}`; glyph.setAttribute('aria-hidden', 'true');
      button.append(glyph, document.createTextNode(' ' + text)); button.disabled = busy;
      button.setAttribute('aria-label', text + ': ' + task.name); actions.append(button);
    });
  }
  function render(data) {
    state = data; rows.replaceChildren(...data.tasks.map(fillRow));
    document.getElementById('celeryEmpty').hidden = data.tasks.some(task => !task.deleted || showDeleted.checked);
    beatStatus(data);
  }
  async function reload() {
    if (busy) return; setBusy(true);
    try { const data = await request(root.dataset.api); render(data); say('Configurazione aggiornata.'); }
    catch (error) { say(error.message, true); }
    finally { setBusy(false); }
  }
  async function change(name, action, extra = {}) {
    if (busy || !state) return false; setBusy(true);
    try {
      const data = await request(root.dataset.update.replace('__task__', encodeURIComponent(name)), {method: 'POST', body: JSON.stringify({revision: state.revision, action, ...extra})});
      state = data;
      if (action === 'frequency') {
        const old = [...rows.children].find(row => row.dataset.id === name);
        old.replaceWith(fillRow(data.tasks.find(task => task.id === name)));
      }
      data.tasks.forEach(task => { const row = [...rows.children].find(item => item.dataset.id === task.id); if (row) updateState(row, task); });
      document.getElementById('celeryEmpty').hidden = data.tasks.some(task => !task.deleted || showDeleted.checked);
      beatStatus(data); say('Salvato. Le modifiche saranno applicate da Celery Beat entro circa 5 secondi.');
      return true;
    } catch (error) { say(error.message, true); confirmError.textContent = error.message; return false; }
    finally { setBusy(false); }
  }
  rows.addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]'); if (!button || busy || !state) return;
    const row = button.closest('tr'), name = row.dataset.id, action = button.dataset.action;
    if (action === 'delete') {
      pending = {name, action};
      document.getElementById('celeryConfirmText').textContent = `Eliminare la schedulazione di “${state.tasks.find(task => task.id === name).name}”? Potrai ripristinarla da Mostra eliminate.`;
      bootstrap.Modal.getOrCreateInstance(modalNode).show(); return;
    }
    if (action === 'frequency') {
      const kind = row.querySelector('[data-field=kind]').value; let frequency;
      if (kind === 'interval') {
        const raw = row.querySelector('[data-field=amount]').value;
        const seconds = Number(raw) * Number(row.querySelector('[data-field=unit]').value);
        if (!raw.trim() || !Number.isInteger(seconds) || seconds < 60 || seconds > 2678400) { say('Inserisci un intervallo tra 1 minuto e 31 giorni.', true); return; }
        frequency = {kind, seconds};
      } else { frequency = {kind}; cronFields.forEach(([field]) => { frequency[field] = row.querySelector(`[data-field=${field}]`).value.trim(); }); }
      await change(name, action, {frequency});
    } else await change(name, action);
  });
  modalNode.addEventListener('show.bs.modal', () => { document.body.classList.add('celery-confirm-open'); });
  modalNode.addEventListener('shown.bs.modal', () => {
    confirmError.textContent = ''; confirmButton.disabled = !pending || busy; confirmButton.textContent = 'Elimina';
    confirmButton.onclick = async () => { if (pending && await change(pending.name, pending.action)) bootstrap.Modal.getInstance(modalNode).hide(); };
  });
  modalNode.addEventListener('hide.bs.modal', event => { if (busy) event.preventDefault(); });
  modalNode.addEventListener('hidden.bs.modal', () => { document.body.classList.remove('celery-confirm-open'); pending = null; confirmButton.onclick = null; confirmButton.disabled = false; confirmError.textContent = ''; });
  document.getElementById('celeryReload').addEventListener('click', reload);
  showDeleted.addEventListener('change', () => { if (!state) return; state.tasks.forEach(task => updateState([...rows.children].find(row => row.dataset.id === task.id), task)); document.getElementById('celeryEmpty').hidden = state.tasks.some(task => !task.deleted || showDeleted.checked); });
  document.getElementById('celeryPauseImports').addEventListener('click', () => change('imports', 'imports_pause'));
  document.getElementById('celeryPlayImports').addEventListener('click', () => change('imports', 'imports_play'));
  const poll = setInterval(async () => {
    if (busy || !state || document.hidden) return;
    const revision = state.revision;
    try { const data = await request(root.dataset.api); if (busy || state.revision !== revision) return; beatStatus(data); if (data.revision !== state.revision) say('Configurazione modificata in un’altra sessione. Premi Aggiorna prima di salvare.', true); }
    catch (_) { beatLabel.textContent = 'Verifica di Celery Beat non disponibile. Premi Aggiorna per riprovare.'; }
  }, 10000);
  window.addEventListener('pagehide', () => clearInterval(poll), {once: true});
  reload();
})();

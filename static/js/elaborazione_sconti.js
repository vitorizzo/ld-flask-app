document.addEventListener('DOMContentLoaded', () => {
  const page = document.querySelector('.discount-page');
  if (!page) return;
  const percent = value => `${Number(value).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  const money = value => Number(value).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  const revisions = new WeakMap();

  function invalidate(form) {
    revisions.set(form, (revisions.get(form) || 0) + 1);
    form.querySelector('.discount-result').hidden = true;
    form.querySelector('.discount-error').hidden = true;
    form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
  }

  function read(input, label, { positive = false, integer = false, max = Infinity } = {}) {
    const raw = input.value.trim().replace(',', '.');
    const value = Number(raw);
    if (!raw || !/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw) || !Number.isFinite(value) || value < 0 || (positive && value === 0) || value > max || (integer && !Number.isInteger(value))) {
      input.setAttribute('aria-invalid', 'true');
      input.focus();
      throw new Error(`${label}: ${integer ? 'inserisci un numero intero' : 'inserisci un numero'} ${positive ? 'maggiore di zero' : 'zero o positivo'}${max !== Infinity ? `, fino a ${max}` : ''}.`);
    }
    return value;
  }

  function addRow(group, values = []) {
    const container = page.querySelector(`[data-rows="${group}"]`);
    const template = document.getElementById(`${container.dataset.rowType}-row-template`);
    const row = template.content.firstElementChild.cloneNode(true);
    row.querySelectorAll('input').forEach((input, index) => { input.value = values[index] ?? ''; });
    container.appendChild(row);
    return row;
  }

  function replaceRows(group, rows) {
    page.querySelector(`[data-rows="${group}"]`).replaceChildren();
    rows.forEach(values => addRow(group, values));
  }

  function discounts(group, complementary = false) {
    return [...page.querySelectorAll(`[data-rows="${group}"] input`)].map((input, index) => {
      const value = read(input, `Sconto ${index + 1}`, { max: 100 });
      if (complementary && value === 100) {
        input.setAttribute('aria-invalid', 'true'); input.focus();
        throw new Error('Con uno sconto già applicato del 100% non è possibile calcolare lo sconto aggiuntivo.');
      }
      return value;
    });
  }

  function goodsTotal(group) {
    const rows = page.querySelectorAll(`[data-rows="${group}"] .discount-input-row`);
    let total = 0;
    rows.forEach((row, index) => {
      const quantity = read(row.querySelector('[data-value="quantity"]'), `Quantità articolo ${index + 1}`);
      const price = read(row.querySelector('[data-value="price"]'), `Valore unitario articolo ${index + 1}`);
      total += quantity * price;
    });
    if (!Number.isFinite(total)) throw new Error('Il valore totale della merce è troppo grande.');
    return total;
  }

  function updateTotals() {
    page.querySelectorAll('[data-total]').forEach(label => {
      const inputs = page.querySelectorAll(`[data-rows="${label.dataset.total}"] .discount-input-row`);
      let valid = true, total = 0;
      inputs.forEach(row => {
        const values = [...row.querySelectorAll('input')].map(input => {
          const raw = input.value.trim().replace(',', '.');
          if (!raw || !/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw)) valid = false;
          return Number(raw);
        });
        total += values[0] * values[1];
      });
      label.textContent = `Totale: ${valid && Number.isFinite(total) ? money(total) : '—'}`;
    });
  }

  page.querySelectorAll('[data-rows]').forEach(container => addRow(container.dataset.rows));
  page.addEventListener('input', event => {
    const form = event.target.closest('[data-calculator]');
    if (form) { invalidate(form); updateTotals(); }
  });

  page.addEventListener('click', event => {
    const tool = event.target.closest('[data-tool]');
    if (tool) {
      page.querySelectorAll('[data-tool]').forEach(button => button.setAttribute('aria-pressed', String(button === tool)));
      page.querySelectorAll('[data-calculator]').forEach(form => { form.hidden = form.dataset.calculator !== tool.dataset.tool; });
    }
    const add = event.target.closest('[data-add-row]');
    if (add) { invalidate(add.closest('form')); addRow(add.dataset.addRow).querySelector('input').focus(); updateTotals(); }
    const remove = event.target.closest('[data-remove-row]');
    if (remove) {
      const form = remove.closest('form'), row = remove.closest('.discount-input-row'), container = row.parentElement;
      invalidate(form);
      if (container.children.length > 1) row.remove();
      else row.querySelectorAll('input').forEach(input => { input.value = ''; });
      container.querySelector('input').focus(); updateTotals();
    }
    const example = event.target.closest('[data-example]');
    if (example) {
      const form = example.closest('form'); invalidate(form);
      switch (form.dataset.calculator) {
        case 'equivalente': replaceRows('equivalente', [[20], [10]]); break;
        case 'complementare': form.elements.target.value = '30'; replaceRows('complementare', [[20]]); break;
        case 'combinazioni': form.elements.paid.value = '3'; form.elements.gift.value = '1'; break;
        case 'merce': replaceRows('paid-goods', [[10, '12,50']]); replaceRows('gift-goods', [[2, '10,00']]); break;
      }
      updateTotals();
    }
  });

  page.querySelectorAll('[data-calculator]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      if (button.disabled) return;
      invalidate(form);
      const revision = revisions.get(form);
      const error = form.querySelector('.discount-error');
      let payload, key, explanation, label = 'Sconto effettivo';
      try {
        switch (form.dataset.calculator) {
          case 'equivalente':
            payload = { sconti: discounts('equivalente') }; key = 'sconto_equivalente';
            explanation = rate => `Su un prezzo iniziale di 100 €, risparmi ${money(rate)} e paghi ${money(100 - rate)}. Gli sconti sono applicati in successione.`;
            break;
          case 'complementare': {
            const target = read(form.elements.target, 'Sconto totale desiderato', { max: 100 });
            payload = { sconto_finale: target, sconti_fissi: discounts('complementare', true) }; key = 'sconto_complementare';
            label = 'Sconto aggiuntivo da applicare';
            explanation = rate => rate < 0
              ? `Gli sconti attuali superano il totale desiderato. Per arrivare al ${percent(target)} serve aumentare il prezzo già scontato del ${percent(-rate)}, anziché applicare un altro sconto.`
              : `Applica questo sconto al prezzo già ridotto: raggiungerai uno sconto totale del ${percent(target)}. Su 100 € iniziali, il prezzo finale sarà ${money(100 - target)}.`;
            break;
          }
          case 'combinazioni':
            payload = { acquistati: read(form.elements.paid, 'Pezzi pagati', { positive: true, integer: true }), omaggio: read(form.elements.gift, 'Pezzi in omaggio', { integer: true }) }; key = 'sconto_combinazione';
            explanation = () => `Paghi ${payload.acquistati} pezzi e ne ricevi ${payload.acquistati + payload.omaggio}: ${payload.omaggio} sono gratuiti. Lo sconto è calcolato sul valore di tutti i pezzi ricevuti.`;
            break;
          case 'merce':
            payload = { val_acquisto: goodsTotal('paid-goods'), val_omaggio: goodsTotal('gift-goods') }; key = 'sconto_merce';
            if (payload.val_acquisto <= 0) throw new Error('Il valore totale della merce pagata deve essere maggiore di zero.');
            explanation = () => `Paghi ${money(payload.val_acquisto)} e ricevi merce per ${money(payload.val_acquisto + payload.val_omaggio)}, inclusi ${money(payload.val_omaggio)} di omaggi. Lo sconto è rapportato al valore totale ricevuto.`;
            break;
        }
        button.disabled = true;
        form.setAttribute('aria-busy', 'true');
        const response = await fetch(form.dataset.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const data = await response.json().catch(() => { throw new Error('La risposta del server non è leggibile. Riprova.'); });
        if (revisions.get(form) !== revision) return;
        if (!response.ok || data.error) throw new Error(data.error || 'Il calcolo non è riuscito. Riprova.');
        const rate = data[key];
        if (typeof rate !== 'number' || !Number.isFinite(rate)) throw new Error('Il server non ha restituito un risultato valido.');
        const result = form.querySelector('.discount-result');
        if (key === 'sconto_complementare' && rate < 0) label = 'Maggiorazione necessaria';
        result.querySelector('[data-result-label]').textContent = label;
        result.querySelector('[data-result-value]').textContent = percent(key === 'sconto_complementare' && rate < 0 ? -rate : rate);
        result.querySelector('[data-result-explanation]').textContent = explanation(rate);
        result.hidden = false;
        result.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } catch (failure) {
        if (revisions.get(form) !== revision) return;
        error.textContent = failure.message || 'Connessione non disponibile. Riprova.';
        error.hidden = false;
      } finally {
        button.disabled = false;
        form.removeAttribute('aria-busy');
      }
    });
  });
});

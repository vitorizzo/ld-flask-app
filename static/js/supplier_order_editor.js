(() => {
  'use strict';
  const page = document.querySelector('.supplier-orders-page');
  if (!page || typeof bootstrap === 'undefined') return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  document.querySelectorAll('[data-create-order-group]').forEach(node => {
    const group = node.dataset.createOrderGroup;
    const status = node.querySelector('[data-order-status]');
    const confirm = node.querySelector('[data-order-save]');
    const close = node.querySelector('[data-order-draft-close]');
    const title = node.querySelector('[data-order-title]');
    const column = node.querySelector('[data-order-column]');
    const list = node.querySelector('.supplier-operational-list');
    const storageKey = `supplier-order:${page.dataset.userId || '0'}:${group}`;
    let card = null, rows = [], baseline = {}, dirty = false, loaded = false, busy = false,
        changed = 0, timer, pending = null, blocked = false, clientKey = '', closing = false, loadId = 0;
    const key = () => globalThis.crypto?.randomUUID?.() || `draft-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    async function api(url, body) {
      const response = await fetch(url, {credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json',Accept:'application/json'},
        ...(body ? {method:'POST',body:JSON.stringify(body)} : {})});
      const result = await response.json();
      if (!response.ok || !result.ok) { const error = Error(result.error || `HTTP ${response.status}`); error.conflict = response.status === 409; throw error; }
      return result;
    }
    function snapshot() {
      return {title:title.value, column_id:Number(column.value),
        products:[...list.querySelectorAll('[data-order-quantity]')].map(input => {
          const wrapper = input.closest('[data-order-product]');
          return {matrix_code:input.dataset.matrixCode,quantity:input.value,
            supplier_code:wrapper.querySelector('[data-supplier-code]').value,
            order_description:wrapper.querySelector('[data-order-description]').value};
        })};
    }
    function backup() {
      try { localStorage.setItem(storageKey,JSON.stringify({card_id:card?.id || null,revision:card?.order_revision || null,clientKey,...snapshot()})); }
      catch (_) { /* The server save still works when device storage is unavailable. */ }
    }
    function clearBackup() { try { localStorage.removeItem(storageKey); } catch (_) {} }
    function setControls() {
      confirm.disabled = !loaded || busy || blocked;
      close.disabled = busy;
      node.querySelectorAll('input,select').forEach(input => input.disabled = !loaded || busy);
    }
    function render(saved, subgroups, local) {
      const quantities = new Map((saved?.order_lines || []).map(line => [line.matrix_code,line.quantity]));
      const localProducts = new Map((local?.products || []).map(row => [row.matrix_code,row]));
      const sections = new Map();
      baseline = {};
      rows.forEach(row => {
        baseline[row.root] = {supplier_code:row.supplier_code || '',order_description:row.order_description || ''};
        const section = row.subgroup_name || subgroups.find(s => s.id === row.subgroup_id)?.name || 'Altri prodotti';
        if (!sections.has(section)) sections.set(section,[]);
        sections.get(section).push(row);
      });
      list.innerHTML = [...sections].map(([name, products]) => `<h6 class="supplier-subgroup-heading">${esc(name)}</h6>` + products.map(row => {
        const edited = localProducts.get(row.root);
        return `<details class="supplier-operational-group ${row.stock <= 0 ? 'is-empty' : ''}" data-order-product>
          <summary class="supplier-operational-row"><div class="supplier-product-main"><div class="supplier-matrix-heading"><strong data-matrix-title>${esc(row.description)}</strong>${!row.retired ? `<button class="btn btn-sm btn-link" type="button" data-matrix-rename data-matrix-code="${esc(row.root)}" title="Rinomina raggruppamento" aria-label="Rinomina ${esc(row.root)}"><i class="fa-regular fa-pen-to-square"></i></button>` : ''}</div><span>Codice interno ${esc(row.root)}${row.retired ? ' · fuori dal gruppo, giacenza storica' : ''}</span></div>
          <div class="supplier-order-amounts"><div class="supplier-stock"><span>${esc(row.stock)}</span><small>giacenza</small></div><div class="supplier-order-quantity"><label>Da ordinare<input class="form-control" data-order-quantity data-matrix-code="${esc(row.root)}" type="number" inputmode="numeric" min="0" max="1000000" step="1" placeholder="0" value="${esc(edited?.quantity ?? quantities.get(row.root) ?? '')}" aria-label="Quantità da ordinare: ${esc(row.description)}"></label></div></div></summary>
          <div class="supplier-order-product-settings"><label>Codice del fornitore<input class="form-control" data-supplier-code maxlength="80" value="${esc(edited?.supplier_code ?? row.supplier_code ?? '')}" placeholder="Obbligatorio per ordinare"></label><label>Descrizione sul PDF<input class="form-control" data-order-description maxlength="200" value="${esc(edited?.order_description ?? row.order_description ?? '')}" placeholder="${esc(row.description)}"></label></div>
          <div class="supplier-variant-list">${(row.variants || []).map(variant => `<div class="supplier-variant-row"><div class="supplier-product-main"><strong>${esc(variant.description)}</strong><span>${esc(variant.cod_art)}</span></div><div class="supplier-stock supplier-stock--small"><span>${esc(variant.stock)}</span><small>giacenza</small></div></div>`).join('')}</div></details>`;
      }).join('')).join('') || '<p>Nessun prodotto nel gruppo.</p>';
      title.value = local?.title ?? saved?.title ?? node.dataset.defaultTitle;
      column.value = String(local?.column_id ?? saved?.column_id ?? column.options[0]?.value ?? '');
      list.querySelectorAll('input').forEach(input => {
        input.addEventListener('click',event => event.stopPropagation());
        input.addEventListener('keydown',event => event.stopPropagation());
      });
    }
    async function load() {
      const request = ++loadId;
      loaded = false; blocked = false; dirty = false; clearTimeout(timer); setControls();
      status.textContent = 'Caricamento ordine e giacenze...';
      let local = null;
      try { local = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (_) {}
      const requested = page.dataset.activeOrderId && page.dataset.activeGroupId === group ? Number(page.dataset.activeOrderId) : local?.card_id;
      try {
        const result = await api(`/supplier-orders/groups/${group}/order-editor${requested ? `?card_id=${requested}` : ''}`);
        if (request !== loadId) return;
        card = result.card; rows = result.rows; clientKey = local?.clientKey || key();
        if (local && ((local.card_id || null) !== (card?.id || null) || (card && local.revision !== card.order_revision))) {
          status.textContent = 'Esiste una copia sul dispositivo diversa dalla versione salvata. Ricarica la versione salvata per scartarla.';
          blocked = true;
        } else {
          status.textContent = card?.is_draft ? 'Bozza ripresa.' : card ? 'Modifica le quantità e conferma per sostituire il PDF.' : 'Codici e descrizioni del fornitore si modificano aprendo il prodotto.';
        }
        render(card,result.subgroups || [],local && !blocked ? local : null);
        node.querySelector('.modal-title').textContent = card ? `Modifica ordine: ${card.title}` : node.dataset.defaultTitle;
        loaded = true; dirty = Boolean(local && !blocked);
        if (dirty) { changed++; timer = setTimeout(() => save(true).catch(() => {}),650); }
      } catch (error) { status.textContent = error.message; }
      setControls();
    }
    function payload(draft) {
      const data = snapshot();
      const lines = [], details = [];
      for (const product of data.products) {
        const input = [...list.querySelectorAll('[data-order-quantity]')].find(i => i.dataset.matrixCode === product.matrix_code);
        const quantity = Number(product.quantity || 0);
        if (!input.validity.valid || !Number.isInteger(quantity) || quantity < 0 || quantity > 1000000) throw Error('Inserisci quantità intere, da 0 a 1000000. La copia sul dispositivo è conservata.');
        if (quantity) {
          lines.push({matrix_code:product.matrix_code,quantity});
          if (!draft && !product.supplier_code.trim()) { input.closest('details').open = true; input.closest('details').querySelector('[data-supplier-code]').focus(); throw Error('Inserisci il codice fornitore per tutti i prodotti da ordinare.'); }
        }
        const old = baseline[product.matrix_code] || {};
        if (product.supplier_code !== old.supplier_code || product.order_description !== old.order_description) details.push({matrix_code:product.matrix_code,supplier_code:product.supplier_code,order_description:product.order_description});
      }
      if (!data.title.trim()) throw Error('Inserisci il titolo ordine.');
      if (!draft && !lines.length) throw Error('Inserisci almeno una quantità da ordinare.');
      return {title:data.title,column_id:data.column_id,lines,product_details:details,draft,client_key:clientKey,
        ...(card ? {card_id:card.id,revision:card.order_revision} : {})};
    }
    async function save(draft) {
      clearTimeout(timer);
      if (pending) { await pending; return save(draft); }
      if (!loaded || blocked) throw Error('Ricarica l’ordine prima di salvare.');
      if (draft && !dirty) return;
      backup();
      let body;
      try { body = payload(draft); } catch (error) { status.textContent = error.message; throw error; }
      const version = changed;
      if (!draft) { busy = true; setControls(); }
      status.textContent = draft ? 'Salvataggio bozza...' : 'Salvataggio e generazione PDF...';
      pending = (async () => {
        try {
          let result = await api(`/supplier-orders/groups/${group}/orders`,body);
          card = result.card;
          if (result.replayed) { body.card_id = card.id; body.revision = card.order_revision; result = await api(`/supplier-orders/groups/${group}/orders`,body); card = result.card; }
          for (const detail of body.product_details) baseline[detail.matrix_code] = {supplier_code:detail.supplier_code,order_description:detail.order_description};
          dirty = changed !== version;
          if (dirty) backup(); else clearBackup();
          status.textContent = draft ? 'Bozza salvata. Puoi chiudere e riprenderla.' : 'Ordine confermato. PDF aggiornato e allegato alla scheda.';
          if (!draft && card.order_pdf_url) {
            const link = document.createElement('a'); link.href = card.order_pdf_url+'?download=1'; link.textContent = ' Scarica PDF'; status.append(link);
          }
        } catch (error) {
          blocked = Boolean(error.conflict); backup();
          status.textContent = `${error.message} La copia sul dispositivo è conservata.`;
          throw error;
        } finally { pending = null; busy = false; setControls(); }
      })();
      await pending;
      if (draft && dirty && !blocked) return save(true);
    }
    node.addEventListener('input',() => {
      if (!loaded || busy || blocked) return;
      dirty = true; changed++; backup(); clearTimeout(timer);
      timer = setTimeout(() => save(true).catch(() => {}),650);
    });
    list.addEventListener('click',async event => {
      const button = event.target.closest('[data-matrix-rename]');
      if (!button) return;
      event.preventDefault(); event.stopPropagation();
      const row = rows.find(row => row.root === button.dataset.matrixCode);
      const proposed = window.prompt('Nome del raggruppamento. Lascia vuoto per ripristinare il nome dell’ultima variante.', row.description);
      if (proposed === null) return;
      button.disabled = true;
      try {
        const result = await api(`/supplier-orders/groups/${group}/matrix-name`,{matrix_code:row.root,display_name:proposed.trim()});
        row.description = result.display_name || row.default_description || row.description;
        button.closest('.supplier-matrix-heading').querySelector('[data-matrix-title]').textContent = row.description;
      } catch (error) { status.textContent = error.message; }
      finally { button.disabled = false; }
    });
    node.addEventListener('shown.bs.modal',() => {
      confirm.textContent = 'Conferma ordine e genera PDF';
      confirm.onclick = () => save(false).catch(() => {});
      close.onclick = () => bootstrap.Modal.getInstance(node).hide();
      node.querySelector('[data-order-reload]').onclick = () => {
        if (window.confirm('Scartare le modifiche conservate sul dispositivo e ricaricare l’ordine salvato?')) { clearBackup(); load(); }
      };
      load();
    });
    node.addEventListener('hide.bs.modal',event => {
      if (busy) { event.preventDefault(); return; }
      if (!closing && (dirty || pending)) {
        event.preventDefault();
        save(true).then(() => { closing = true; bootstrap.Modal.getInstance(node).hide(); })
          .catch(() => { if (window.confirm('La bozza non è stata salvata sul server. Chiudere conservando la copia su questo dispositivo?')) { closing = true; bootstrap.Modal.getInstance(node).hide(); } });
      }
    });
    node.addEventListener('hidden.bs.modal',() => {
      clearTimeout(timer); loadId++; closing = false; loaded = false;
      confirm.onclick = null; close.onclick = null;
      if (page.dataset.activeGroupId === group) page.dataset.activeOrderId = '';
    });
    window.addEventListener('beforeunload',event => {
      if (dirty || pending || busy) { backup(); event.preventDefault(); event.returnValue = ''; }
    });
  });
})();

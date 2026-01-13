// editor.js
document.addEventListener('DOMContentLoaded', () => {
  console.log('Editor JS loaded');

  // 1) Riferimenti DOM
  const sel        = document.getElementById('connection_id');
  const btnNew     = document.getElementById('btn-new');
  const btnEdit    = document.getElementById('btn-edit-meta');
  const manageLink = document.getElementById('manage-actions');
  const saveBtn    = document.getElementById('saveBtn');
  const editor     = document.getElementById('editor');
  const metaCon    = document.getElementById('meta-form-container');
  const metaForm   = document.getElementById('meta-form');
  const inputs     = {
    board_id:     document.getElementById('in-board_id'),
    board_name:   document.getElementById('in-board_name'),
    api_key:      document.getElementById('in-api_key'),
    token:        document.getElementById('in-token'),
    callback_url: document.getElementById('in-callback_url'),
  };
  let currentId = null;
  let instance  = null;


  // Popup (overlay) per scegliere la bacheca
  function ensureBoardPickerModal() {
    if (document.getElementById('trello-board-modal')) return;

    const overlay = document.createElement('div');
    overlay.id = 'trello-board-modal';
    overlay.style.cssText = `
      position:fixed; inset:0; z-index:9999;
      background:rgba(0,0,0,.45);
      display:none; align-items:center; justify-content:center;
      padding:16px;
    `;

    const panel = document.createElement('div');
    panel.style.cssText = `
      width:min(560px, 100%);
      background:#fff;
      border:1px solid #ddd;
      border-radius:10px;
      padding:16px;
      box-shadow:0 10px 30px rgba(0,0,0,.25);
      font-family:inherit;
    `;

    panel.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; gap:12px;">
        <h3 style="margin:0;">Seleziona bacheca Trello</h3>
        <button type="button" id="trello-board-cancel-x"
                style="font-size:18px; line-height:1; border:0; background:transparent; cursor:pointer;">×</button>
      </div>

      <div style="margin-top:12px;">
        <label style="display:block; margin-bottom:6px;">Bacheca</label>
        <select id="trello-board-select" style="width:100%; padding:8px;">
          <option value="">Caricamento...</option>
        </select>
        <div id="trello-board-error" style="display:none; margin-top:10px; color:#b00020;"></div>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:16px;">
        <button type="button" id="trello-board-cancel" style="padding:8px 12px;">Annulla</button>
        <button type="button" id="trello-board-confirm" style="padding:8px 12px;">Crea connessione</button>
      </div>
    `;

    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    const close = () => { overlay.style.display = 'none'; };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    panel.querySelector('#trello-board-cancel-x').addEventListener('click', close);
    panel.querySelector('#trello-board-cancel').addEventListener('click', close);
  }


  // Apre popup -> carica boards -> crea connessione -> seleziona la nuova connessione nella combo
  async function openBoardPickerAndCreateConnection() {
    ensureBoardPickerModal();

    const overlay   = document.getElementById('trello-board-modal');
    const selBoard  = document.getElementById('trello-board-select');
    const errBox    = document.getElementById('trello-board-error');
    const btnConfirm = document.getElementById('trello-board-confirm');

    // reset UI
    errBox.style.display = 'none';
    errBox.textContent = '';
    selBoard.innerHTML = `<option value="">Caricamento...</option>`;
    btnConfirm.disabled = true;
    overlay.style.display = 'flex';

    // 1) carico lista board dal backend
    let boards = [];
    try {
      const r = await fetch('/trello/boards', { headers: { 'Accept': 'application/json' } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      boards = await r.json();
    } catch (e) {
      errBox.textContent = `Errore caricando bacheche: ${String(e)}`;
      errBox.style.display = 'block';
      selBoard.innerHTML = `<option value="">(errore)</option>`;
      return;
    }

    // popola select
    selBoard.innerHTML =
      `<option value="">-- Seleziona --</option>` +
      boards.map(b => `<option value="${b.id}">${b.name}</option>`).join('');

    // abilita “Crea” solo dopo selezione
    selBoard.addEventListener('change', () => {
      btnConfirm.disabled = !selBoard.value;
    });

    // evita multi-handler se riapri più volte la modale
    btnConfirm.onclick = null;

    // 2) conferma: crea connessione e aggiorna la combo
    btnConfirm.onclick = async () => {
      const board_id   = selBoard.value;
      const board_name = selBoard.options[selBoard.selectedIndex]?.text || '';
      if (!board_id) return;

      btnConfirm.disabled = true;
      errBox.style.display = 'none';
      errBox.textContent = '';

      try {
        const resp = await fetch('/trello/connection', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ board_id, board_name })
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw data;

        // aggiungo option e seleziono la connessione creata
        const opt = document.createElement('option');
        opt.value = data.id;
        opt.text  = `${board_name} (ID:${data.id})`;
        sel.appendChild(opt);
        sel.value = String(data.id);

        overlay.style.display = 'none';

        // trigger del tuo handler change: carica dati connessione + schema
        sel.dispatchEvent(new Event('change'));
      } catch (e) {
        errBox.textContent = `Errore creando connessione: ${JSON.stringify(e)}`;
        errBox.style.display = 'block';
        btnConfirm.disabled = false;
      }
    };
  }


  // 2) Funzione per creare un nodo nel canvas
  function addNode(id, label, x, y) {
    const n = document.createElement('div');
    n.className = 'node';
    n.id        = id;
    n.innerText = label;
    n.style.cssText = `
      position:absolute;
      left:${x}px; top:${y}px;
      width:150px; padding:8px;
      border:1px solid #333;
      background:#fff; color:#333;
      text-align:center; cursor:move;
    `;
    editor.appendChild(n);
    instance.draggable(n, { containment: 'parent' });
    instance.makeSource(n,    { anchor: "BottomCenter", maxConnections: -1 });
    instance.makeTarget(n,    { anchor: "TopCenter",    maxConnections: -1 });
  }

  // 3) Inizializza jsPlumb e disegna nodi/connessioni
  function initJsPlumb(schema, isNew = false) {
    editor.innerHTML = '';
    if (instance) instance.reset();
    instance = jsPlumb.getInstance({
      Connector: ["Straight"],
      Anchors: ["BottomCenter","TopCenter"],
      Endpoint: ["Dot", { radius: 4 }],
      PaintStyle: { strokeWidth: 2 },
      ConnectionOverlays: [
        ["Arrow", { width:10, length:10, location:1 }]
      ]
    });

    // se nuova connessione e schema vuoto, crea i due nodi base
    if (isNew && schema.nodes.length === 0) {
      addNode('trigger', 'Trigger Trello', 50,  50);
      addNode('action',  'Azione',        300, 200);
    }

    // ridisegna nodi da schema
    schema.nodes.forEach(n => addNode(n.id, n.label, n.x, n.y));

    // ridisegna connessioni da schema
    schema.connections.forEach(c =>
      instance.connect({ source: c.sourceId, target: c.targetId })
    );
  }

  // 4) Carica le connessioni e popola la select
  fetch('/trello/connection')
    .then(r => r.json())
    .then(list => {
      list.forEach(c => {
        const o = document.createElement('option');
        o.value = c.id;
        o.text  = `${c.board_name} (ID:${c.id})`;
        sel.appendChild(o);
      });
    });

  // 5) Handler cambio selezione
  sel.addEventListener('change', () => {
    currentId = sel.value || null;
    btnEdit.disabled        = !currentId;
    manageLink.style.display = 'none';
    console.log('change handler triggered, currentId =', currentId);

    if (currentId) {
      fetch(`/trello/connection/${currentId}`)
        .then(r => r.json())
        .then(data => {
          // popola e mostra form metadati
          Object.keys(inputs).forEach(f => inputs[f].value = data[f]);
          metaCon.style.display = 'block';

          // imposta link Gestisci Azioni
          manageLink.href           = `/trello/connection/${currentId}/actions`;
          manageLink.style.display  = 'inline-block';

          // ridisegna schema salvato
          initJsPlumb(data.schema, false);
        });
    }
    else {
      // reset UI per nuova connessione
      metaCon.style.display = 'none';
      initJsPlumb({ nodes:[], connections:[] }, true);
    }
  });

  // 6) Salvataggio metadati
  metaForm.addEventListener('submit', e => {
    e.preventDefault();
    const payload = {};
    Object.keys(inputs).forEach(f => payload[f] = inputs[f].value);

    fetch(`/trello/connection/${currentId}`, {
      method:  'PUT',
      headers: {'Content-Type':'application/json'},
      body:    JSON.stringify(payload)
    })
    .then(r => {
      if (!r.ok) throw new Error('Errore salvando dati');
      alert('Dati connessione aggiornati!');
      // nascondi il form e resetta
      metaCon.style.display = 'none';
      currentId             = null;
    })
    .catch(err => alert(err));
  });

  // 7) Pulsanti di controllo
  btnNew.addEventListener('click', () => {
    openBoardPickerAndCreateConnection();
  });
  btnEdit.addEventListener('click', () => {
    window.location = `/trello/connection/editor/${currentId}`;
  });
  saveBtn.addEventListener('click', () => {
    if (!currentId) {
      alert('Seleziona o crea prima una connessione.');
      return;
    }

    const nodes = Array.from(editor.querySelectorAll('.node')).map(n => ({
      id:    n.id,
      x:     parseInt(n.style.left),
      y:     parseInt(n.style.top),
      label: n.innerText
    }));
    const connections = instance.getAllConnections().map(c => ({
      sourceId: c.sourceId,
      targetId: c.targetId
    }));

    const schema = { nodes, connections };

    fetch(`/trello/connection/${currentId}`, {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ schema })
    })
    .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
    .then(() => alert('Schema aggiornato'))
    .catch(e => alert("Errore: " + JSON.stringify(e)));
  });

  // 8) Primo init: nuova connessione con nodi base
  initJsPlumb({ nodes:[], connections:[] }, true);
});

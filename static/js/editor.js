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
    sel.value = '';
    sel.dispatchEvent(new Event('change'));
  });
  btnEdit.addEventListener('click', () => {
    window.location = `/trello/connection/editor/${currentId}`;
  });
  saveBtn.addEventListener('click', () => {
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
    let url    = '/trello/connection';
    let method = 'POST';
    if (currentId) {
      url    += `/${currentId}`;
      method  = 'PUT';
    } else {
      // nuovi: chiedi metadati via prompt
      schema.board_id     = prompt("Board ID:");
      schema.board_name   = prompt("Board name:");
      schema.api_key      = prompt("API key:");
      schema.token        = prompt("Token:");
      schema.callback_url = prompt("Callback URL:");
    }
    fetch(url, {
      method, headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ schema })
    })
    .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
    .then(res => {
      alert(currentId ? 'Schema aggiornato' : 'Connessione creata ID ' + res.id);
      if (!currentId) window.location = '/trello/connections';
    })
    .catch(e => alert("Errore: " + JSON.stringify(e)));
  });

  // 8) Primo init: nuova connessione con nodi base
  initJsPlumb({ nodes:[], connections:[] }, true);
});

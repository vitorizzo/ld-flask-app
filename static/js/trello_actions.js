// trello_actions.js
document.addEventListener('DOMContentLoaded', () => {
  const connId = window.TRELLO_CONN_ID;
  const tbody  = document.querySelector('#actions-table tbody');

  // ---------------------------------------------------------------------------
  // 3.1) Costanti
  // ---------------------------------------------------------------------------
  const AVAILABLE_TRIGGERS = [
    'copyCard',
    'createCard',
    'updateCard',
    'moveCard',
    'commentCard',
    'moveToList',
    'addLabelToCard'
  ];

  const AVAILABLE_ACTIONS = [
    'sendEmail',
    'addComment',
    'mirrorCard',
    'customizeCard',
    'sendSlackMessage',
    'serviceComments'
  ];

  const PLACEHOLDER_LIST = [
    '{{user}}',
    '{{card.name}}',
    '{{card.id}}',
    '{{card.url}}',
    '{{listbefore.name}}',
    '{{listafter.name}}',
    '{{list.name}}',
    '{{list.id}}',
    '{{board.name}}',
    '{{board.id}}',
    '{{comment.text}}'
  ];

  const TRIGGER_FIELDS = {
    moveToList: [
      { name: 'list_id', label: 'ID Lista di Destinazione', type: 'text', required: true, placeholder: '640c3f36b45cebb4ad052254' }
    ],
    // altri trigger in futuro...
  };

  const ACTION_FIELDS = {
    sendEmail: [
      { name: 'to', type: 'email', label: 'To', required: true },
      { name: 'subject', type: 'text', label: 'Subject', required: true },
      { name: 'body', type: 'textarea', label: 'Body', required: true }
    ],
    addComment: [
      { name: 'comment', type: 'textarea', label: 'Commento', required: true, placeholder: 'Esempio: La card {{card.name}} è stata spostata da {{user}}' }
    ],
    mirrorCard: [
      { name: 'target_board_id', type: 'text', label: 'Board ID destinazione', required: true },
      { name: 'target_list_id', type: 'text', label: 'Lista destinazione', required: true }
    ],
    sendSlackMessage: [
      { name: 'channel', type: 'text', label: 'Canale Slack', required: true, placeholder: '#nome-canale' },
      { name: 'message', type: 'textarea', label: 'Messaggio', required: true, placeholder: 'Esempio: La card {{card.name}} è stata spostata da {{user}}' }
    ]
  };

  // ---------------------------------------------------------------------------
  // 3.2) Riferimenti al form
  // ---------------------------------------------------------------------------
  const btnAdd          = document.getElementById('btn-add-action');
  const formContainer   = document.getElementById('action-form-container');
  const formTitle       = document.getElementById('action-form-title');
  const triggerSelect   = document.getElementById('trigger-type');
  const actionSelect    = document.getElementById('action-type');
  const triggerParamsDiv= document.getElementById('trigger-params');
  const actionParamsDiv = document.getElementById('action-params');
  const actionForm      = document.getElementById('action-form');
  const cancelAction    = document.getElementById('cancel-action');
  const ordineInput     = document.getElementById('ordine');

  let editingActionId = null;

  // ---------------------------------------------------------------------------
  // Helper: render standard fields (input/textarea)
  // ---------------------------------------------------------------------------
  function renderFields(fieldDefs, container) {
    container.innerHTML = '';
    fieldDefs.forEach(field => {
      const wrapper = document.createElement('div');

      const label = document.createElement('label');
      label.textContent = field.label + ': ';

      let input;
      if (field.type === 'textarea') {
        input = document.createElement('textarea');
        input.rows = 3;

        // placeholder selector
        const selector = document.createElement('select');
        selector.innerHTML = `<option value="">+ Inserisci variabile...</option>`;
        PLACEHOLDER_LIST.forEach(ph => {
          const opt = document.createElement('option');
          opt.value = ph;
          opt.textContent = ph;
          selector.appendChild(opt);
        });

        selector.addEventListener('change', () => {
          const ph = selector.value;
          if (!ph) return;
          const start = input.selectionStart;
          const end   = input.selectionEnd;
          const text  = input.value;
          input.value = text.slice(0, start) + ph + text.slice(end);
          input.focus();
          input.selectionEnd = start + ph.length;
          selector.value = '';
        });

        wrapper.appendChild(selector);
      } else {
        input = document.createElement('input');
        input.type = field.type;
      }

      input.name = field.name;
      if (field.required) input.required = true;
      if (field.placeholder) input.placeholder = field.placeholder;

      label.appendChild(input);
      wrapper.appendChild(label);
      container.appendChild(wrapper);
    });
  }

  // ---------------------------------------------------------------------------
  // Helper: fetch JSON
  // ---------------------------------------------------------------------------
  async function fetchJson(url) {
    const r = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!r.ok) throw new Error(`HTTP ${r.status} on ${url}`);
    return await r.json();
  }

  // ---------------------------------------------------------------------------
  // Helper: select builders
  // ---------------------------------------------------------------------------
  function makeSelect({ id, label, placeholder = "-- Seleziona --" }) {
    const wrap = document.createElement("div");

    const lab = document.createElement("label");
    lab.textContent = label;
    lab.setAttribute("for", id);
    wrap.appendChild(lab);

    const sel = document.createElement("select");
    sel.id = id;
    sel.className = "form-select";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = placeholder;
    sel.appendChild(opt0);

    wrap.appendChild(sel);
    return { wrap, sel };
  }

  function fillSelect(sel, items, { valueKey = "id", textKey = "name" } = {}) {
    while (sel.options.length > 1) sel.remove(1);
    for (const it of items) {
      const o = document.createElement("option");
      o.value = it[valueKey];
      o.textContent = it[textKey];
      sel.appendChild(o);
    }
  }

  async function mountBoardListSelectors(container, {
    boardFieldName,
    listFieldName,
    initialBoardId = "",
    initialListId = ""
  }) {
    const { wrap: boardWrap, sel: boardSel } = makeSelect({
      id: `${boardFieldName}__select`,
      label: "Board",
      placeholder: "-- Seleziona Board --"
    });

    const { wrap: listWrap, sel: listSel } = makeSelect({
      id: `${listFieldName}__select`,
      label: "Lista",
      placeholder: "-- Seleziona Lista --"
    });
    listSel.disabled = true;

    // Hidden inputs (nomi attesi dal backend)
    const boardHidden = document.createElement("input");
    boardHidden.type = "hidden";
    boardHidden.name = boardFieldName;
    boardHidden.value = initialBoardId;

    const listHidden = document.createElement("input");
    listHidden.type = "hidden";
    listHidden.name = listFieldName;
    listHidden.value = initialListId;

    container.appendChild(boardWrap);
    container.appendChild(listWrap);
    container.appendChild(boardHidden);
    container.appendChild(listHidden);

    const boards = await fetchJson("/trello/boards");
    fillSelect(boardSel, boards);

    if (initialBoardId) boardSel.value = initialBoardId;

    async function loadLists(boardId, preselectListId = "") {
      listSel.disabled = true;
      fillSelect(listSel, []);
      listHidden.value = "";

      if (!boardId) return;

      const lists = await fetchJson(`/trello/boards/${boardId}/lists`);
      fillSelect(listSel, lists);
      listSel.disabled = false;

      if (preselectListId) {
        listSel.value = preselectListId;
        listHidden.value = preselectListId;
      }
    }

    await loadLists(boardSel.value, initialListId);

    boardSel.addEventListener("change", async () => {
      const bid = boardSel.value;
      boardHidden.value = bid;
      await loadLists(bid, "");
    });

    listSel.addEventListener("change", () => {
      listHidden.value = listSel.value;
    });
  }

  // ---------------------------------------------------------------------------
  // Dynamic enhancement: sostituisce input con select (board->lists)
  // ---------------------------------------------------------------------------
  async function enhanceDynamicFields(config = {}) {
    // mirrorCard: target_board_id + target_list_id
    if (actionSelect.value === "mirrorCard") {
      actionParamsDiv.innerHTML = "";
      await mountBoardListSelectors(actionParamsDiv, {
        boardFieldName: "target_board_id",
        listFieldName: "target_list_id",
        initialBoardId: config.target_board_id || "",
        initialListId: config.target_list_id || ""
      });
    }

    // moveToList: board_id + list_id (per ora li facciamo scegliere entrambi)
    if (triggerSelect.value === "moveToList") {
      triggerParamsDiv.innerHTML = "";
      await mountBoardListSelectors(triggerParamsDiv, {
        boardFieldName: "board_id",
        listFieldName: "list_id",
        initialBoardId: config.board_id || "",
        initialListId: config.list_id || ""
      });
    }
  }

  // ---------------------------------------------------------------------------
  // 3.3) Popola le tendine trigger/action
  // ---------------------------------------------------------------------------
  AVAILABLE_TRIGGERS.forEach(t => {
    const o = document.createElement('option');
    o.value = t; o.text = t;
    triggerSelect.appendChild(o);
  });

  AVAILABLE_ACTIONS.forEach(a => {
    const o = document.createElement('option');
    o.value = a; o.text = a;
    actionSelect.appendChild(o);
  });

  // ---------------------------------------------------------------------------
  // 1) FETCH lista azioni e popola la tabella
  // ---------------------------------------------------------------------------
  fetch(`/trello/actions?connection_id=${connId}`)
    .then(r => r.json())
    .then(list => {
      list.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${a.id}</td>
          <td>${a.ordine || ''}</td>
          <td>${a.trigger_type}</td>
          <td>${a.action_type}</td>
          <td><pre>${JSON.stringify(a.config_json, null, 2)}</pre></td>
          <td>
            <button data-id="${a.id}" class="btn-edit">Modifica</button>
            <button data-id="${a.id}" class="btn-del">Elimina</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    });

  // ---------------------------------------------------------------------------
  // 2) Delegation per Modifica/Elimina
  // ---------------------------------------------------------------------------
  tbody.addEventListener('click', e => {
    const btn = e.target;
    const id  = btn.dataset.id;

    if (btn.classList.contains('btn-del')) {
      if (!confirm('Sei sicuro di eliminare?')) return;
      fetch(`/trello/actions/${id}`, { method: 'DELETE' })
        .then(() => {
          formContainer.style.display = 'none';
          editingActionId = null;
          triggerParamsDiv.innerHTML = '';
          actionParamsDiv.innerHTML = '';
          document.getElementById('save-action').style.display = 'inline-block';
          document.getElementById('update-action').style.display = 'none';
          location.reload();
        });
    }

    if (btn.classList.contains('btn-edit')) {
      fetch(`/trello/actions/${id}`)
        .then(r => r.json())
        .then(async action => {
          editingActionId = id;
          ordineInput.value = action.ordine || 0;
          formTitle.textContent = 'Modifica Azione';
          formContainer.style.display = 'block';

          triggerSelect.value = action.trigger_type;
          actionSelect.value  = action.action_type;

          // disegna campi base
          renderFields(TRIGGER_FIELDS[action.trigger_type] || [], triggerParamsDiv);
          renderFields(ACTION_FIELDS[action.action_type]  || [], actionParamsDiv);

          const config = action.config_json || {};

          // sostituisce con select dove serve + prefill
          await enhanceDynamicFields(config);

          // riempi i valori rimanenti (input/textarea e hidden inputs)
          [triggerParamsDiv, actionParamsDiv].forEach(container => {
            Array.from(container.querySelectorAll('input,textarea')).forEach(fld => {
              if (config[fld.name] !== undefined) {
                fld.value = config[fld.name];
              }
            });
          });

          document.getElementById('save-action').style.display = 'none';
          document.getElementById('update-action').style.display = 'inline-block';
        });
    }
  });

  // ---------------------------------------------------------------------------
  // 3.4) Mostra/Nasconde form
  // ---------------------------------------------------------------------------
  btnAdd.addEventListener('click', () => {
    formTitle.textContent = 'Nuova Azione';
    actionForm.reset();
    triggerParamsDiv.innerHTML = '';
    actionParamsDiv.innerHTML = '';
    editingActionId = null;

    document.getElementById('save-action').style.display = 'inline-block';
    document.getElementById('update-action').style.display = 'none';

    formContainer.style.display = 'block';
  });

  cancelAction.addEventListener('click', () => {
    formContainer.style.display = 'none';
    editingActionId = null;
    triggerParamsDiv.innerHTML = '';
    actionParamsDiv.innerHTML = '';
    document.getElementById('save-action').style.display = 'inline-block';
    document.getElementById('update-action').style.display = 'none';
  });

  // ---------------------------------------------------------------------------
  // 3.5) Al cambio trigger/action, disegna campi e poi enhance
  // ---------------------------------------------------------------------------
  actionSelect.addEventListener('change', async () => {
    const fields = ACTION_FIELDS[actionSelect.value] || [];
    renderFields(fields, actionParamsDiv);
    await enhanceDynamicFields({});
  });

  triggerSelect.addEventListener('change', async () => {
    const fields = TRIGGER_FIELDS[triggerSelect.value] || [];
    renderFields(fields, triggerParamsDiv);
    await enhanceDynamicFields({});
  });

  // ---------------------------------------------------------------------------
  // 3.6) Submit del form
  // ---------------------------------------------------------------------------
  actionForm.addEventListener('submit', e => {
    e.preventDefault();

    const params = {};
    [triggerParamsDiv, actionParamsDiv].forEach(container => {
      Array.from(container.querySelectorAll('input,textarea')).forEach(fld => {
        params[fld.name] = fld.value;
      });
    });

    if (!triggerSelect.value || !actionSelect.value) {
      alert('Seleziona sia un trigger che un’azione.');
      return;
    }

    const payload = {
      connection_id: connId,
      ordine: parseInt(ordineInput.value) || 0,
      trigger_type: triggerSelect.value,
      action_type: actionSelect.value,
      config_json: params
    };

    const url    = editingActionId ? `/trello/actions/${editingActionId}` : '/trello/actions';
    const method = editingActionId ? 'PUT' : 'POST';

    fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(r => {
        if (!r.ok) return r.json().then(err => Promise.reject(err));
        return r.json();
      })
      .then(() => {
        alert(editingActionId ? 'Azione aggiornata con successo!' : 'Azione creata con successo!');
        formContainer.style.display = 'none';
        editingActionId = null;
        triggerParamsDiv.innerHTML = '';
        actionParamsDiv.innerHTML = '';
        document.getElementById('save-action').style.display = 'inline-block';
        document.getElementById('update-action').style.display = 'none';
        location.reload();
      })
      .catch(err => alert(JSON.stringify(err)));
  });
});

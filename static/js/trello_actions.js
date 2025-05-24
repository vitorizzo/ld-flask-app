// static/js/trello_actions.js
document.addEventListener('DOMContentLoaded', () => {
  const connId = window.TRELLO_CONN_ID;
  const tbody  = document.querySelector('#actions-table tbody');

  // 1) FETCH lista azioni
  fetch(`/trello/actions?connection_id=${connId}`)
    .then(r => r.json())
    .then(list => {
      // se non ci sono azioni, la tabella rimane vuota
      list.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${a.id}</td>
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
    })
    .catch(err => console.error('Errore fetching actions:', err));

  // 2) Delegation per Modifica / Elimina
  tbody.addEventListener('click', e => {
    const btn = e.target;
    const id  = btn.dataset.id;
    if (!id) return;

    if (btn.classList.contains('btn-del')) {
      if (!confirm('Sei sicuro di eliminare questa azione?')) return;
      fetch(`/trello/actions/${id}`, { method: 'DELETE' })
        .then(() => location.reload())
        .catch(err => console.error('Errore delete action:', err));
    }

    if (btn.classList.contains('btn-edit')) {
      // qui potrai aprire il form di modifica
      alert('Implementa qui la modifica per action ' + id);
    }
  });

  // 3) Nuova Azione
  document.getElementById('btn-add-action')
    .addEventListener('click', () => {
      const trigger = prompt('Trigger type:');
      const action  = prompt('Action type:');
      const cfgText = prompt('Config JSON:');
      let cfg;
      try {
        cfg = JSON.parse(cfgText);
      } catch {
        return alert('JSON di configurazione non valido');
      }
      fetch('/trello/actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connection_id: connId,
          trigger_type:  trigger,
          action_type:   action,
          config_json:   cfg
        })
      })
      .then(() => location.reload())
      .catch(err => console.error('Errore creating action:', err));
    });
});
// 0) Lista di trigger e azioni supportate
const AVAILABLE_TRIGGERS = [
  'createCard',
  'updateCard',
  'moveCard',
  'commentCard'
];

const AVAILABLE_ACTIONS = [
  'sendEmail',
  'addComment',
  'mirrorCard'
];

// 1) Riferimenti al form
const formContainer = document.getElementById('action-form-container');
const triggerSelect = document.getElementById('trigger-type');
const actionSelect  = document.getElementById('action-type');
const paramsDiv     = document.getElementById('action-params');
const formTitle     = document.getElementById('action-form-title');
const saveActionBtn = document.getElementById('save-action');
const cancelAction  = document.getElementById('cancel-action');
const actionForm    = document.getElementById('action-form');

// 2) Popola le tendine
AVAILABLE_TRIGGERS.forEach(t => {
  const o = document.createElement('option');
  o.value = t;
  o.text  = t;
  triggerSelect.appendChild(o);
});

AVAILABLE_ACTIONS.forEach(a => {
  const o = document.createElement('option');
  o.value = a;
  o.text  = a;
  actionSelect.appendChild(o);
});

// 3) Show/Hide form
document.getElementById('btn-add-action').addEventListener('click', () => {
  formTitle.textContent = 'Nuova Azione';
  actionForm.reset();
  paramsDiv.innerHTML = '';
  formContainer.style.display = 'block';
});

cancelAction.addEventListener('click', () => {
  formContainer.style.display = 'none';
});

// 4) Al cambio di “azione” mostriamo i campi necessari (davvero minimal; aggiorneremo presto)
actionSelect.addEventListener('change', () => {
  paramsDiv.innerHTML = '';
  const at = actionSelect.value;
  if (!at) return;
  if (at === 'sendEmail') {
    paramsDiv.innerHTML = `
      <div>
        <label>To:      <input type="email" name="to"     required></label>
      </div>
      <div>
        <label>Subject: <input type="text"  name="subject" required></label>
      </div>
      <div>
        <label>Body:    <textarea name="body" rows="3" required></textarea></label>
      </div>
    `;
  }
  else if (at === 'addComment') {
    paramsDiv.innerHTML = `
      <div>
        <label>Commento:<textarea name="comment" rows="2" required></textarea></label>
      </div>
    `;
  }
  else if (at === 'mirrorCard') {
    paramsDiv.innerHTML = `
      <div>
        <label>Board ID destinazione: <input type="text" name="target_board_id" required></label>
      </div>
      <div>
        <label>Lista destinazione:     <input type="text" name="target_list_id" required></label>
      </div>
    `;
  }
});

// 5) Submit del form: serializziamo in JSON e inviamo al server
actionForm.addEventListener('submit', e => {
  e.preventDefault();
  const cfg = { connection_id: connId, trigger_type: triggerSelect.value, action_type: actionSelect.value };
  // raccogliamo tutti gli input/textarea
  Array.from(paramsDiv.querySelectorAll('input,textarea')).forEach(fld => {
    cfg[fld.name] = fld.value;
  });

  fetch('/trello/actions', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(cfg)
  })
  .then(r => {
    if (!r.ok) throw new Error('Errore creando action');
    return r.json();
  })
  .then(() => location.reload())
  .catch(err => alert(err));
});

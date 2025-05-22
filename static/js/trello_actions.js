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

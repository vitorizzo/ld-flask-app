  <script src="https://unpkg.com/jsplumb@2.15.6/dist/js/jsplumb.min.js"></script>
  <script>
  document.addEventListener('DOMContentLoaded', () => {
    const connId = {{ connection.id }};
    const tbody  = document.querySelector('#actions-table tbody');

    // 1) FETCH lista azioni
    fetch(`/trello/actions?connection_id=${connId}`)
      .then(r => r.json())
      .then(list => {
        list.forEach(a => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${a.id}</td>
            <td>${a.trigger_type}</td>
            <td>${a.action_type}</td>
            <td><pre>${JSON.stringify(a.config_json)}</pre></td>
            <td>
              <button data-id="${a.id}" class="btn-edit">Modifica</button>
              <button data-id="${a.id}" class="btn-del">Elimina</button>
            </td>
          `;
          tbody.appendChild(tr);
        });
      });

    // 2) Eventi di click su Modifica / Elimina (delegation)
    tbody.addEventListener('click', e => {
      const btn = e.target;
      const id  = btn.dataset.id;
      if (btn.classList.contains('btn-del')) {
        if (!confirm('Sei sicuro di eliminare?')) return;
        fetch(`/trello/actions/${id}`, { method: 'DELETE' })
          .then(() => location.reload());
      }
      if (btn.classList.contains('btn-edit')) {
        // qui potremo aprire un form di modifica
        alert('Implementa qui la modifica per action ' + id);
      }
    });

    // 3) “Nuova Azione”
    document.getElementById('btn-add-action')
      .addEventListener('click', () => {
        // apri un prompt minimale per test
        const trigger = prompt('Trigger type:');
        const action  = prompt('Action type:');
        const cfg     = prompt('Config JSON:');
        fetch('/trello/actions', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            connection_id: connId,
            trigger_type: trigger,
            action_type: action,
            config_json: JSON.parse(cfg)
          })
        })
        .then(() => location.reload());
      });
  });
  </script>

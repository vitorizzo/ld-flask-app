// trello_actions.js
document.addEventListener('DOMContentLoaded', () => {
    const connId = window.TRELLO_CONN_ID;
    const tbody  = document.querySelector('#actions-table tbody');

    // 1) FETCH lista azioni e popola la tabella
    fetch(`/trello/actions?connection_id=${connId}`)
    .then(r => r.json())
    .then(list => {
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
    });

    // 2) Delegation per Modifica/Elimina
    tbody.addEventListener('click', e => {
    const btn = e.target;
    const id  = btn.dataset.id;
    if (btn.classList.contains('btn-del')) {
        if (!confirm('Sei sicuro di eliminare?')) return;
        fetch(`/trello/actions/${id}`, { method: 'DELETE' })
            .then(() => location.reload());
        }
        if (btn.classList.contains('btn-edit')) {
            alert('Implementa qui la modifica per action ' + id);
        }
    });

    //
    // ————————————————
    // 3) NUOVA AZIONE: form grafico
    //

    // 3.1) Costanti
    const AVAILABLE_TRIGGERS = [
        'createCard', 'updateCard', 'moveCard', 'commentCard', 'moveToList'
    ];
    const AVAILABLE_ACTIONS = [
        'sendEmail', 'addComment', 'mirrorCard', 'sendSlackMessage'
    ];

    const TRIGGER_FIELDS = {
        moveToList: [
            { name: 'list_id', label: 'ID Lista di Destinazione', type: 'text', required: true }
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
            { name: 'comment', type: 'textarea', label: 'Commento', required: true }
        ],
        mirrorCard: [
            { name: 'target_board_id', type: 'text', label: 'Board ID destinazione', required: true },
            { name: 'target_list_id', type: 'text', label: 'Lista destinazione', required: true }
        ],
        sendSlackMessage: [
            { name: 'channel', type: 'text', label: 'Canale Slack', required: true },
            { name: 'message', type: 'textarea', label: 'Messaggio', required: true }
        ]
    };


    // 3.2) Riferimenti al form
    const btnAdd = document.getElementById('btn-add-action');
    const formContainer = document.getElementById('action-form-container');
    const formTitle = document.getElementById('action-form-title');
    const triggerSelect = document.getElementById('trigger-type');
    const actionSelect = document.getElementById('action-type');
    const triggerParamsDiv = document.getElementById('trigger-params');
    const actionParamsDiv = document.getElementById('action-params');
    const actionForm = document.getElementById('action-form');
    const cancelAction = document.getElementById('cancel-action');

    // 3.3) Popola le tendine
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

    // 3.4) Mostra il form al click “Nuova Azione”
    btnAdd.addEventListener('click', () => {
        formTitle.textContent = 'Nuova Azione';
        actionForm.reset();
        paramsDiv.innerHTML = '';
        formContainer.style.display = 'block';
    });
    cancelAction.addEventListener('click', () => {
        formContainer.style.display = 'none';
    });

    // 3.5) Al cambio di “azione”, disegna i campi specifici
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
            } else {
                input = document.createElement('input');
                input.type = field.type;
            }
            input.name = field.name;
            if (field.required) input.required = true;
            label.appendChild(input);
            wrapper.appendChild(label);
            container.appendChild(wrapper);
        });
    }


    // Al cambio di “azione”
    actionSelect.addEventListener('change', () => {
        const fields = ACTION_FIELDS[actionSelect.value] || [];
        renderFields(fields, actionParamsDiv);
    });

    triggerSelect.addEventListener('change', () => {
        const fields = TRIGGER_FIELDS[triggerSelect.value] || [];
        renderFields(fields, triggerParamsDiv);
    });



    // 3.6) Submit del form: invia la POST e ricarica
    actionForm.addEventListener('submit', e => {
        e.preventDefault();

        // 1) raccogli i parametri nel “config_json”
        const params = {};
        [triggerParamsDiv, actionParamsDiv].forEach(container => {
            Array.from(container.querySelectorAll('input,textarea')).forEach(fld => {
                params[fld.name] = fld.value;
            });
        });


        // 2) costruisci il payload completo
        const payload = {
            connection_id: connId,
            trigger_type:  triggerSelect.value,
            action_type:   actionSelect.value,
            config_json:   params      // <— qui!
        };

        // 3) invia
        fetch('/trello/actions', {
            method:  'POST',
            headers: {'Content-Type':'application/json'},
            body:    JSON.stringify(payload)
        })
        .then(r => {
            if (!r.ok) return r.json().then(err=>Promise.reject(err));
                return r.json();
            })
        .then(() => location.reload())
        .catch(err => alert(JSON.stringify(err)));
    });

});

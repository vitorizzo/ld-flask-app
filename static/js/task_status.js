document.addEventListener('DOMContentLoaded', function () {
    const wrapper = document.getElementById('task-status-wrapper');
    const progressBar = document.getElementById('task-status-progress');
    const label = document.getElementById('task-status-label');
    const details = document.getElementById('task-status-details');
    const expandIcon = document.getElementById('task-status-expand');
    const taskList = document.getElementById('task-status-list');
    const actions = document.getElementById('task-status-actions');
    const clearErrorsButton = document.getElementById('task-status-clear-errors');

    if (!wrapper || !progressBar || !label || !details || !expandIcon || !taskList) return;

    let expanded = false;

    const escapeHtml = (value) => String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');

    async function fetchStatus() {
        try {
            const res = await fetch('/task/status');
            const data = await res.json();

            const tasks = data.tasks || [];

            wrapper.classList.remove('d-none');

            if (tasks.length > 0) {

                let totalProgress = 0;
                let activeCount = 0;
                let errorCount = 0;
                taskList.innerHTML = '';

                tasks.forEach(task => {
                    const taskId = task.task_id || task.id || "";
                    const progress = Number(task.progress || 0);
                    const state = (task.stato || task.status || "").toString();
                    const error = (task.errore || task.error || "").toString();
                    const isError = ["errore", "error", "fallito", "failed", "residuo", "stale"].some(value => state.toLowerCase().includes(value));
                    const isTerminal = Boolean(task.terminal) || isError;
                    if (isTerminal) errorCount += 1;
                    else {
                        activeCount += 1;
                        totalProgress += progress;
                    }

                    const li = document.createElement('li');
                    li.classList.add('list-group-item');
                    if (isError) li.classList.add('task-status-error');
                    li.innerHTML = `
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="task-status-copy">
                                <strong>${escapeHtml(task.name || "Task")}</strong>
                                <br><small class="text-muted">${escapeHtml(taskId)}</small> - ${progress}% - ${escapeHtml(state || "stato sconosciuto")}
                                ${task.legacy ? `<br><small class="text-warning">Risultato storico privo di data</small>` : ""}
                                ${error ? `<br><small class="text-danger">${escapeHtml(error)}</small>` : ""}
                            </span>
                            <div class="btn-group btn-group-sm" role="group">
                                <button class="btn btn-outline-info task-details-button" type="button">Dettagli</button>
                                <button class="btn btn-outline-danger task-stop-button" type="button">${isTerminal ? 'Rimuovi' : 'Stop'}</button>
                            </div>
                        </div>
                    `;
                    li.querySelector('.task-details-button')?.addEventListener('click', () => fetchTaskDetails(taskId));
                    li.querySelector('.task-stop-button')?.addEventListener('click', () => killTask(taskId, isTerminal));
                    taskList.appendChild(li);
                });

                const avgProgress = activeCount ? Math.floor(totalProgress / activeCount) : 0;
                progressBar.style.width = `${avgProgress}%`;
                label.innerText = `Attivi: ${activeCount} | Errori/residui: ${errorCount}${activeCount ? ` | ${avgProgress}%` : ''}`;
                actions?.classList.toggle('d-none', errorCount === 0);
            } else {
                taskList.innerHTML = '<li class="list-group-item task-status-empty">Nessun processo attivo o in errore.</li>';
                progressBar.style.width = '0%';
                label.innerText = 'Processi in background: nessuna attività';
                actions?.classList.add('d-none');
            }

        } catch (err) {
            console.error('Errore durante il polling dello stato task:', err);
            wrapper.classList.remove('d-none');
            label.innerText = 'Monitor processi non disponibile';
        }
    }

    fetchStatus();
    setInterval(fetchStatus, 2000);

    const toggleDetails = function () {
        expanded = !expanded;
        details.classList.toggle('d-none', !expanded);
        expandIcon.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        const icon = expandIcon.querySelector('i');
        icon?.classList.toggle('bi-chevron-down', !expanded);
        icon?.classList.toggle('bi-chevron-up', expanded);
    };
    expandIcon.addEventListener('click', toggleDetails);
    document.getElementById('task-status-bar')?.addEventListener('click', function (event) {
        if (event.target.closest('button')) return;
        toggleDetails();
    });

    clearErrorsButton?.addEventListener('click', async function () {
        if (!confirm('Rimuovere dal monitor errori e stati residui? I processi attivi non saranno toccati.')) return;
        clearErrorsButton.disabled = true;
        try {
            const response = await fetch('/task_manage/clear_errors', {method: 'POST', headers: {'Accept': 'application/json'}});
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
            await fetchStatus();
        } catch (error) {
            alert(`Impossibile rimuovere errori e stati residui: ${error}`);
        } finally {
            clearErrorsButton.disabled = false;
        }
    });
});

async function fetchTaskDetails(taskId) {
    try {
        const res = await fetch(`/task_manage/status/${encodeURIComponent(taskId)}`);
        const data = await res.json();
        alert(`Stato del task:\n\nID: ${data.id}\nStato: ${data.status}\nSuccesso: ${data.successful}\nRisultato: ${data.result}`);
    } catch (err) {
        alert("Errore nel recuperare i dettagli del task.");
        console.error(err);
    }
}

async function killTask(taskId, removeOnly = false) {
    const verb = removeOnly ? 'rimuovere dal monitor' : 'terminare';
    if (!confirm(`Sei sicuro di voler ${verb} il task ${taskId}?`)) return;
    try {
        const res = await fetch(`/task_manage/kill/${encodeURIComponent(taskId)}`, {
            method: "POST",
            headers: {"Content-Type": "application/json", "Accept": "application/json"},
            body: JSON.stringify({remove_only: removeOnly}),
        });
        const data = await res.json();
        alert(data.message);
    } catch (err) {
        alert("Errore nel terminare il task.");
        console.error(err);
    }
}

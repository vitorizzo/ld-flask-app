document.addEventListener('DOMContentLoaded', function () {
    const wrapper = document.getElementById('task-status-wrapper');
    const progressBar = document.getElementById('task-status-progress');
    const label = document.getElementById('task-status-label');
    const details = document.getElementById('task-status-details');
    const expandIcon = document.getElementById('task-status-expand');
    const taskList = document.getElementById('task-status-list');

    let expanded = false;

    async function fetchStatus() {
        try {
            const res = await fetch('/task/status');
            const data = await res.json();

            const tasks = data.tasks || [];

            if (tasks.length > 0) {
                wrapper.classList.remove('d-none');

                let totalProgress = 0;
                taskList.innerHTML = '';

                tasks.forEach(task => {
                    totalProgress += task.progress;
                    const li = document.createElement('li');
                    li.classList.add('list-group-item');
                    li.innerHTML = `
                        <div class="d-flex justify-content-between align-items-center">
                            <span><strong>${task.name || "Task"}</strong><br><small class="text-muted">${task.task_id}</small> — ${task.progress}%</span>
                            <div class="btn-group btn-group-sm" role="group">
                                <button class="btn btn-outline-info" onclick="fetchTaskDetails('${task.id}')">📄</button>
                                <button class="btn btn-outline-danger" onclick="killTask('${task.id}')">🛑</button>
                            </div>
                        </div>
                    `;
                    taskList.appendChild(li);
                });

                const avgProgress = Math.floor(totalProgress / tasks.length);
                progressBar.style.width = `${avgProgress}%`;
                label.innerText = `Processi attivi: ${tasks.length} | Avanzamento medio: ${avgProgress}%`;
            } else {
                wrapper.classList.add('d-none');
            }

        } catch (err) {
            console.error('Errore durante il polling dello stato task:', err);
        }
    }

    setInterval(fetchStatus, 2000);  // ogni 2 secondi

    // toggle dettagli
    expandIcon.addEventListener('click', function () {
        expanded = !expanded;
        details.classList.toggle('d-none', !expanded);
        expandIcon.classList.toggle('bi-chevron-down', !expanded);
        expandIcon.classList.toggle('bi-chevron-up', expanded);
    });
});

async function fetchTaskDetails(taskId) {
    try {
        const res = await fetch(`/task_manage/status/${taskId}`);
        const data = await res.json();
        alert(`🧾 Stato del task:\n\nID: ${data.id}\nStato: ${data.stato}\nSuccesso: ${data.successful}\nRisultato: ${data.result}`);
    } catch (err) {
        alert("Errore nel recuperare i dettagli del task.");
        console.error(err);
    }
}

async function killTask(taskId) {
    if (!confirm(`Sei sicuro di voler terminare il task ${taskId}?`)) return;
    try {
        const res = await fetch(`/task_manage/kill/${taskId}`, { method: "POST" });
        const data = await res.json();
        alert(`🛑 ${data.message}`);
    } catch (err) {
        alert("Errore nel terminare il task.");
        console.error(err);
    }
}

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
                    li.innerText = `${task.name}: ${task.progress}%`;
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

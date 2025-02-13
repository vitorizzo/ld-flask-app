const socket = io.connect('/import');

socket.on('progress_update', function(data) {
    const progressBar = document.getElementById('progress-bar');
    const progressLabel = document.getElementById('progress-label');

    progressBar.value = data.progress;
    if (data.progress < 100) {
        progressLabel.textContent = `Importazione in corso: ${Math.round(data.progress)}%`;
    } else {
        progressLabel.textContent = "Importazione completata!";
    }
});
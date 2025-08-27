let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
    // Previeni prompt automatico
    e.preventDefault();
    deferredPrompt = e;
});

// Gestione pulsante Android
document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("android-install-btn");
    const status = document.getElementById("android-status");

    if (!btn) return;

    btn.addEventListener("click", async () => {
        if (!deferredPrompt) {
            status.textContent = "Non è possibile installare l’app ora.";
            return;
        }
        deferredPrompt.prompt();
        const choiceResult = await deferredPrompt.userChoice;
        status.textContent = `Hai scelto: ${choiceResult.outcome}`;
        deferredPrompt = null;
    });
});

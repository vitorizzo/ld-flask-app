document.addEventListener("DOMContentLoaded", () => {
    const banner = document.getElementById("install-banner");
    const closeBtn = document.getElementById("install-close");
    const installBtn = document.getElementById("install-btn");

    if (!banner) return;

    if (isPwaInstalled()) {
        // Se già installata, assicuriamoci che resti nascosta
        banner.style.display = "none";
        console.log("✅ PWA is already installed → banner nascosto.");
        return;
    }

    // Se non installata → mostra banner
    banner.style.display = "flex";
    console.log("❌ PWA not installed → banner mostrato.");

    // Chiudi banner
    closeBtn.addEventListener("click", () => {
        banner.classList.add("fade-out");
        setTimeout(() => banner.remove(), 500);
    });

    // Bottone “Scopri come”
    installBtn.addEventListener("click", () => {
        window.location.href = "/installation/app_installation";
    });
});


function isPwaInstalled() {
    // ✅ Android/Windows/desktop (Chrome, Edge, ecc.)
    if (window.matchMedia('(display-mode: standalone)').matches) {
        console.log("PWA is installed (Android/Windows/desktop standalone mode).");
        return true;
    }

    // ✅ iOS Safari
    if (window.navigator.standalone === true) {
        console.log("PWA is installed (iOS standalone mode).");
        return true;
    }

    // ✅ Chrome/Edge su desktop possono anche essere "windowed"
    if (window.matchMedia('(display-mode: minimal-ui)').matches) {
        console.log("PWA is installed (minimal-ui mode).");
        return true;
    }

    // In tutti gli altri casi presumiamo che NON sia installata
    console.log("PWA is not installed.");
    return false;
}
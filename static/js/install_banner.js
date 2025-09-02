document.addEventListener("DOMContentLoaded", () => {
    const banner = document.getElementById("install-banner");
    const closeBtn = document.getElementById("install-close");
    const installBtn = document.getElementById("install-btn");

    console.log(banner, closeBtn, installBtn);

    if (!banner) return;

    // Mostra banner solo se PWA non è installata
    if (not isPwaInstalled()) {
        banner.visibility = "visible";
        console.log("PWA is not already installed.");
        return;
    }

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
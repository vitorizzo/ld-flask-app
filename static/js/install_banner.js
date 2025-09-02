document.addEventListener("DOMContentLoaded", () => {
    const banner = document.getElementById("install-banner");
    const closeBtn = document.getElementById("install-close");
    const installBtn = document.getElementById("install-btn");

    console.log(banner, closeBtn, installBtn);

    if (!banner) return;

    // Mostra banner solo se PWA non è installata
    if (isPwaInstalled()) {
        banner.remove();
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
    return window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true; // per iOS
}

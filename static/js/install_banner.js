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

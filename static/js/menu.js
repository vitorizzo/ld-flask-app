document.addEventListener("DOMContentLoaded", function () {
    console.log("JS caricato!");

    function isMobileView() {
        return window.innerWidth < 992;
    }

    function enableBootstrapDropdowns() {
        document.querySelectorAll(".dropdown-item").forEach((item) => {
            if (isMobileView()) {
                item.removeAttribute("data-bs-toggle"); // Su mobile, gestiamo tutto manualmente
            } else {
                item.setAttribute("data-bs-toggle", "dropdown"); // Su desktop, ripristiniamo Bootstrap
            }
        });
    }

    enableBootstrapDropdowns(); // Applica la configurazione iniziale

    // Aggiorna il comportamento al cambio di dimensione della finestra
    window.addEventListener("resize", enableBootstrapDropdowns);

    // Usa event delegation per intercettare i click su tutti i dropdown
    document.body.addEventListener("click", function (e) {
        var link = e.target.closest(".dropdown-item");

        if (!link) return; // Se il click non è su un dropdown-item, esci

        var parentLi = link.closest(".dropdown");
        var menu = link.nextElementSibling; // Il sottomenu associato

        if (!menu || !menu.classList.contains("dropdown-menu")) return;

        console.log("Cliccato su:", link.textContent.trim());

        if (isMobileView()) {
            e.preventDefault(); // Evita il comportamento predefinito sui link con figli

            var isOpen = menu.classList.contains("show");

            // Chiude solo i dropdown dello stesso livello, lasciando aperti quelli superiori
            var parentMenu = parentLi.closest(".dropdown-menu");
            if (parentMenu) {
                parentMenu.querySelectorAll(":scope > .dropdown-menu.show").forEach(function (openMenu) {
                    if (openMenu !== menu) {
                        openMenu.classList.remove("show");
                        openMenu.style.display = "none"; // Nasconde il menu chiuso
                    }
                });
            }

            // Alterna lo stato del menu
            if (isOpen) {
                menu.classList.remove("show");
                menu.style.display = "none"; // Nasconde il menu chiuso
                console.log("Chiuso:", menu);
            } else {
                menu.classList.add("show");
                menu.style.display = "block"; // Forza la visibilità
                menu.style.opacity = "1";
                menu.style.visibility = "visible";
                console.log("Aperto:", menu);
            }

            console.log("Stato aggiornato del menu:", menu.classList.contains("show"));
        }
    });

    // Chiude tutti i dropdown quando si ridimensiona la finestra (reset su desktop)
    window.addEventListener("resize", function () {
        if (!isMobileView()) {
            document.querySelectorAll(".dropdown-menu").forEach(function (menu) {
                menu.classList.remove("show");
                menu.style.display = "none"; // Nasconde i menu quando si torna a desktop
            });
        }
    });
});

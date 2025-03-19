document.addEventListener("DOMContentLoaded", function () {
    console.log("JS caricato!");

    function isMobileView() {
        return window.innerWidth < 992;
    }

    function enableBootstrapDropdowns() {
        document.querySelectorAll(".dropdown-toggle").forEach((link) => {
            if (isMobileView()) {
                // Su mobile rimuovo l'attributo e, se esiste, distruggo l'istanza Bootstrap
                link.removeAttribute("data-bs-toggle");
                if (window.bootstrap && bootstrap.Dropdown) {
                    var instance = bootstrap.Dropdown.getInstance(link);
                    if (instance) {
                        instance.dispose();
                    }
                }
            } else {
                // Su desktop imposto l'attributo e inizializzo il dropdown
                link.setAttribute("data-bs-toggle", "dropdown");
                if (window.bootstrap && bootstrap.Dropdown) {
                    var instance = bootstrap.Dropdown.getInstance(link);
                    if (instance) {
                        instance.dispose();
                    }
                    new bootstrap.Dropdown(link);
                }
            }
        });
    }

    enableBootstrapDropdowns();

    // Al resize si aggiornano le impostazioni e, se siamo su desktop, rimuovo le proprietà inline
    window.addEventListener("resize", function () {
        enableBootstrapDropdowns();
        if (!isMobileView()) {
            document.querySelectorAll(".dropdown-menu").forEach(function (menu) {
                menu.classList.remove("show");
                menu.removeAttribute("style");
            });
        }
    });

    // Event delegation: gestiamo il click sui trigger solo in mobile
    document.body.addEventListener("click", function (e) {
        var link = e.target.closest(".dropdown-toggle");
        if (!link) return;
        if (!isMobileView()) return; // Lascia il comportamento nativo in desktop

        var parentLi = link.closest(".dropdown");
        var menu = link.nextElementSibling;
        if (!menu || !menu.classList.contains("dropdown-menu")) return;

        e.preventDefault();
        console.log("Cliccato su:", link.textContent.trim());
        var isOpen = menu.classList.contains("show");

        // Chiude eventuali altri dropdown dello stesso livello
        var parentMenu = parentLi.closest(".dropdown-menu");
        if (parentMenu) {
            parentMenu.querySelectorAll(":scope > .dropdown-menu.show").forEach(function (openMenu) {
                if (openMenu !== menu) {
                    openMenu.classList.remove("show");
                    openMenu.removeAttribute("style");
                }
            });
        }

        // Alterna la visibilità del menu
        if (isOpen) {
            menu.classList.remove("show");
            menu.style.display = "none";
            console.log("Chiuso:", menu);
        } else {
            menu.classList.add("show");
            menu.style.display = "block";
            menu.style.opacity = "1";
            menu.style.visibility = "visible";
            console.log("Aperto:", menu);
        }
        console.log("Stato aggiornato del menu:", menu.classList.contains("show"));
    });
});

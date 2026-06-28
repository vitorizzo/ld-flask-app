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

document.addEventListener("DOMContentLoaded", function () {
    var profileDropdown = document.getElementById("profileDropdown");
    var profileMenu = document.querySelector(".dropdown-menu[aria-labelledby='profileDropdown']");

    if (!profileDropdown) {
        console.error("❌ Errore: #profileDropdown non trovato nel DOM!");
        return;
    }
    if (!profileMenu) {
        console.error("❌ Errore: dropdown-menu non trovata per #profileDropdown!");
        return;
    }

    console.log("✅ Inizializzazione del menu profilo...");

    // Associa manualmente il menu profilo a Bootstrap
    var dropdownInstance = bootstrap.Dropdown.getOrCreateInstance(profileDropdown);
    dropdownInstance._menu = profileMenu; // FORZA l'associazione del menu

    function isMobileMenuProfile() {
        return window.matchMedia("(max-width: 820px), (hover: none) and (pointer: coarse)").matches;
    }

    function toggleMobileProfileMenu(event) {
        if (!isMobileMenuProfile()) return false;
        event.preventDefault();
        event.stopPropagation();
        var isOpen = profileMenu.classList.contains("show");
        profileMenu.classList.toggle("show", !isOpen);
        profileMenu.style.display = isOpen ? "none" : "block";
        profileMenu.style.opacity = isOpen ? "" : "1";
        profileMenu.style.visibility = isOpen ? "" : "visible";
        profileDropdown.setAttribute("aria-expanded", isOpen ? "false" : "true");
        return true;
    }

    profileDropdown.addEventListener("click", function (event) {
        if (toggleMobileProfileMenu(event)) return;
        event.preventDefault();
        console.log("✅ Click su profileDropdown, avvio toggle...");

        // Riassegna la dropdown-menu prima di eseguire toggle
        var instance = bootstrap.Dropdown.getOrCreateInstance(profileDropdown);
        instance._menu = profileMenu;
        instance.toggle();
    });

    var profileRow = profileDropdown.closest(".nav-item")?.querySelector(".d-flex");
    if (profileRow) {
        profileRow.style.cursor = "pointer";
        profileRow.addEventListener("click", function (event) {
            if (event.target.closest(".dropdown-menu")) return;
            if (event.target.closest("#profileDropdown")) return;
            event.preventDefault();
            if (isMobileMenuProfile()) {
                toggleMobileProfileMenu(event);
            } else {
                profileDropdown.click();
            }
        });
    }
});

document.addEventListener("DOMContentLoaded", function () {
    var navbarToggler = document.querySelector(".navbar-toggler");
    var navbarCollapse = document.querySelector(".navbar-collapse");

    if (navbarToggler && navbarCollapse) {
        var touchStartX = 0;
        var touchStartY = 0;
        var touchStartTime = 0;
        var pointerStartX = 0;
        var pointerStartY = 0;
        var pointerStartTime = 0;

        function isMobileDrawerEnabled() {
            return window.matchMedia("(max-width: 820px), (hover: none) and (pointer: coarse)").matches;
        }

        function showDrawer() {
            bootstrap.Collapse.getOrCreateInstance(navbarCollapse).show();
        }

        function hideDrawer() {
            var instance = bootstrap.Collapse.getInstance(navbarCollapse) || bootstrap.Collapse.getOrCreateInstance(navbarCollapse);
            instance.hide();
        }

        function handleDrawerSwipe(startX, startY, endX, endY, elapsed) {
            var deltaX = endX - startX;
            var deltaY = endY - startY;
            var horizontalSwipe = Math.abs(deltaX) >= 70 && Math.abs(deltaY) <= 90 && elapsed <= 900;
            if (!horizontalSwipe) return;

            var isOpen = navbarCollapse.classList.contains("show");
            var startsInOpenZone = startX <= Math.max(120, window.innerWidth * 0.12);
            if (!isOpen && startsInOpenZone && deltaX > 0) {
                showDrawer();
            } else if (isOpen && deltaX < 0) {
                hideDrawer();
            }
        }

        navbarCollapse.addEventListener("show.bs.collapse", function () {
            document.body.classList.add("mobile-menu-open");
        });

        navbarCollapse.addEventListener("hide.bs.collapse", function () {
            document.body.classList.remove("mobile-menu-open");
        });

        navbarCollapse.addEventListener("hidden.bs.collapse", function () {
            document.body.classList.remove("mobile-menu-open");
        });

        navbarToggler.addEventListener("click", function () {
            if (navbarCollapse.classList.contains("show")) {
                // Se il menu è aperto, chiudilo
                bootstrap.Collapse.getInstance(navbarCollapse).hide();
            } else {
                // Se il menu è chiuso, aprilo
                bootstrap.Collapse.getOrCreateInstance(navbarCollapse).show();
            }
        });

        document.addEventListener("touchstart", function (event) {
            if (!isMobileDrawerEnabled() || event.touches.length !== 1) return;
            var touch = event.touches[0];
            touchStartX = touch.clientX;
            touchStartY = touch.clientY;
            touchStartTime = Date.now();
        }, { passive: true });

        document.addEventListener("touchend", function (event) {
            if (!isMobileDrawerEnabled() || !touchStartTime || event.changedTouches.length !== 1) return;
            var touch = event.changedTouches[0];
            handleDrawerSwipe(touchStartX, touchStartY, touch.clientX, touch.clientY, Date.now() - touchStartTime);
            touchStartTime = 0;
        }, { passive: true });

        document.addEventListener("pointerdown", function (event) {
            if (!isMobileDrawerEnabled() || event.pointerType !== "touch") return;
            pointerStartX = event.clientX;
            pointerStartY = event.clientY;
            pointerStartTime = Date.now();
        }, { passive: true });

        document.addEventListener("pointerup", function (event) {
            if (!isMobileDrawerEnabled() || event.pointerType !== "touch" || !pointerStartTime) return;
            handleDrawerSwipe(pointerStartX, pointerStartY, event.clientX, event.clientY, Date.now() - pointerStartTime);
            pointerStartTime = 0;
        }, { passive: true });
    }
});



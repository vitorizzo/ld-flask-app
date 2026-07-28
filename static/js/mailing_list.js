(() => {
    "use strict";

    const modals = Array.from(document.querySelectorAll("[data-mailing-modal]"));
    const modalInstances = new Map();

    modals.forEach((modalElement) => {
        document.body.appendChild(modalElement);
        const instance = bootstrap.Modal.getOrCreateInstance(modalElement);
        modalInstances.set(modalElement.id, instance);

        modalElement.addEventListener("shown.bs.modal", () => {
            modalElement.querySelectorAll("button[type='submit']").forEach((button) => {
                button.disabled = false;
                if (!button.dataset.defaultText) {
                    button.dataset.defaultText = button.innerHTML;
                }
            });
        });

        modalElement.addEventListener("hidden.bs.modal", () => {
            modalElement.querySelectorAll("button[type='submit']").forEach((button) => {
                button.disabled = false;
                if (button.dataset.defaultText) {
                    button.innerHTML = button.dataset.defaultText;
                }
            });
        });
    });

    document.querySelectorAll("[data-mailing-open-modal]").forEach((button) => {
        button.addEventListener("click", () => {
            modalInstances.get(button.dataset.mailingOpenModal)?.show();
        });
    });

    const forms = document.querySelectorAll("[data-mailing-filter-form]");

    forms.forEach((form) => {
        const categories = Array.from(form.querySelectorAll("[data-mailing-category]"));
        const allChildren = Array.from(form.querySelectorAll("[data-mailing-child]"));
        const summary = form.querySelector("[data-mailing-filter-summary]");

        const syncSummary = () => {
            if (!summary) return;
            const selected = allChildren.filter((checkbox) => checkbox.checked).length;
            summary.textContent = `${selected} di ${allChildren.length} sottocategorie selezionate`;
        };

        const syncCategory = (category) => {
            const parent = category.querySelector("[data-mailing-parent]");
            const children = Array.from(category.querySelectorAll("[data-mailing-child]"));
            if (!parent || !children.length) return;

            const checkedCount = children.filter((checkbox) => checkbox.checked).length;
            parent.checked = checkedCount === children.length;
            parent.indeterminate = checkedCount > 0 && checkedCount < children.length;
            parent.setAttribute(
                "aria-checked",
                parent.indeterminate ? "mixed" : String(parent.checked)
            );
        };

        const syncTree = () => {
            categories.forEach(syncCategory);
            syncSummary();
        };

        categories.forEach((category) => {
            const parent = category.querySelector("[data-mailing-parent]");
            const children = Array.from(category.querySelectorAll("[data-mailing-child]"));
            const toggle = category.querySelector(".mailing-filter-toggle");
            const childList = category.querySelector(".mailing-filter-children");

            parent?.addEventListener("change", () => {
                children.forEach((checkbox) => {
                    checkbox.checked = parent.checked;
                });
                parent.indeterminate = false;
                syncTree();
            });

            children.forEach((checkbox) => {
                checkbox.addEventListener("change", syncTree);
            });

            toggle?.addEventListener("click", () => {
                if (!childList) return;
                const expanded = toggle.getAttribute("aria-expanded") === "true";
                toggle.setAttribute("aria-expanded", String(!expanded));
                childList.hidden = expanded;
            });
        });

        form.querySelector("[data-mailing-select-all]")?.addEventListener("click", () => {
            allChildren.forEach((checkbox) => {
                checkbox.checked = true;
            });
            syncTree();
        });

        form.querySelector("[data-mailing-clear-all]")?.addEventListener("click", () => {
            allChildren.forEach((checkbox) => {
                checkbox.checked = false;
            });
            syncTree();
        });

        syncTree();
    });

    const requestedModalId = window.mailingRequestedModal === "lists"
        ? "mailingListsModal"
        : window.mailingRequestedModal === "campaigns"
            ? "mailingCampaignModal"
            : window.mailingRequestedModal === "history"
                ? "mailingHistoryModal"
            : null;
    if (requestedModalId) {
        modalInstances.get(requestedModalId)?.show();
    }
})();

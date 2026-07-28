(() => {
    "use strict";

    const modals = Array.from(document.querySelectorAll("[data-mailing-modal]"));
    const modalInstances = new Map();
    const campaignModal = document.getElementById("mailingCampaignModal");
    const campaignForm = campaignModal?.querySelector("[data-mailing-campaign-form]");
    const campaignTitle = campaignModal?.querySelector("[data-mailing-campaign-title]");
    const campaignHeading = campaignModal?.querySelector("[data-mailing-campaign-heading]");
    const campaignSubmit = campaignModal?.querySelector("[data-mailing-campaign-submit]");
    const campaignCancel = campaignModal?.querySelector("[data-mailing-campaign-cancel]");

    const resetCampaignForm = () => {
        if (!campaignForm) return;
        campaignForm.reset();
        campaignForm.action = campaignForm.dataset.createAction;
        campaignTitle.textContent = "Nuova campagna";
        campaignHeading.textContent = "Crea campagna";
        campaignSubmit.textContent = "Salva bozza";
        campaignSubmit.disabled = false;
        campaignCancel.classList.add("d-none");
        delete campaignForm.dataset.editingCampaignId;
    };

    const editCampaign = (campaignId) => {
        const campaign = window.mailingCampaignDetails?.[String(campaignId)];
        if (!campaignForm || !campaign) return;

        campaignForm.action = campaign.editAction;
        campaignForm.elements.mailing_list_id.value = String(campaign.mailingListId ?? "");
        campaignForm.elements.subject.value = campaign.subject ?? "";
        campaignForm.elements.account_code.value = campaign.accountCode ?? "general";
        campaignForm.elements.html_body.value = campaign.htmlBody ?? "";
        campaignForm.dataset.editingCampaignId = String(campaign.id);
        campaignTitle.textContent = "Modifica campagna";
        campaignHeading.textContent = `Modifica: ${campaign.subject}`;
        campaignSubmit.textContent = "Salva modifiche";
        campaignSubmit.disabled = false;
        campaignCancel.classList.remove("d-none");
        modalInstances.get("mailingCampaignModal")?.show();
    };

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
            if (modalElement.id === "mailingCampaignModal") {
                resetCampaignForm();
            }
        });
    });

    document.querySelectorAll("[data-mailing-open-modal]").forEach((button) => {
        button.addEventListener("click", () => {
            if (button.hasAttribute("data-mailing-new-campaign")) {
                resetCampaignForm();
            }
            modalInstances.get(button.dataset.mailingOpenModal)?.show();
        });
    });

    document.querySelectorAll("[data-mailing-edit-campaign]").forEach((element) => {
        element.addEventListener("click", (event) => {
            if (
                element.matches("tr")
                && event.target.closest("form, button, a, details, input, select, textarea")
            ) {
                return;
            }
            event.stopPropagation();
            editCampaign(element.dataset.mailingEditCampaign);
        });
        if (element.matches("tr")) {
            element.addEventListener("keydown", (event) => {
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                editCampaign(element.dataset.mailingEditCampaign);
            });
        }
    });

    campaignCancel?.addEventListener("click", resetCampaignForm);

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

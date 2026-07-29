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
    const campaignAttachments = campaignModal?.querySelector("[data-mailing-existing-attachments]");
    const templateModal = document.getElementById("mailingTemplatesModal");
    const templateForm = templateModal?.querySelector("[data-mailing-template-form]");
    const templateHeading = templateModal?.querySelector("[data-mailing-template-heading]");
    const templateSubmit = templateModal?.querySelector("[data-mailing-template-submit]");
    const templateCancel = templateModal?.querySelector("[data-mailing-template-cancel]");
    const scheduleMode = campaignForm?.querySelector("[data-mailing-schedule-mode]");

    const syncScheduleFields = () => {
        if (!campaignForm || !scheduleMode) return;
        const mode = scheduleMode.value;
        const visibleFields = new Set();
        if (mode !== "manual") visibleFields.add("start");
        if (["periodic", "multiple", "until"].includes(mode)) visibleFields.add("interval");
        if (mode === "multiple") visibleFields.add("max-runs");
        if (mode === "until") visibleFields.add("end");

        campaignForm.querySelectorAll("[data-schedule-field]").forEach((field) => {
            const visible = visibleFields.has(field.dataset.scheduleField);
            field.classList.toggle("d-none", !visible);
            field.querySelectorAll("input, select").forEach((control) => {
                control.required = visible;
            });
        });
    };

    const renderCampaignAttachments = (attachments = []) => {
        if (!campaignAttachments) return;
        campaignAttachments.replaceChildren();
        campaignAttachments.classList.toggle("d-none", attachments.length === 0);
        attachments.forEach((attachment) => {
            const row = document.createElement("div");
            row.className = "d-flex flex-wrap justify-content-between align-items-center gap-2 border rounded p-2";
            const label = document.createElement("span");
            label.textContent = `${attachment.name} (${Math.max(1, Math.ceil(attachment.size / 1024))} KB)`;
            const form = document.createElement("form");
            form.method = "post";
            form.action = attachment.deleteAction;
            form.addEventListener("submit", (event) => {
                if (!window.confirm(`Rimuovere l'allegato ${attachment.name}?`)) {
                    event.preventDefault();
                }
            });
            const button = document.createElement("button");
            button.type = "submit";
            button.className = "btn btn-sm btn-outline-danger";
            button.textContent = "Rimuovi";
            form.appendChild(button);
            row.append(label, form);
            campaignAttachments.appendChild(row);
        });
    };

    const resetCampaignForm = () => {
        if (!campaignForm) return;
        campaignForm.reset();
        campaignForm.action = campaignForm.dataset.createAction;
        campaignTitle.textContent = "Nuova campagna";
        campaignHeading.textContent = "Crea campagna";
        campaignSubmit.textContent = "Salva bozza";
        campaignSubmit.disabled = false;
        campaignCancel.classList.add("d-none");
        renderCampaignAttachments();
        syncScheduleFields();
        delete campaignForm.dataset.editingCampaignId;
    };

    const editCampaign = (campaignId) => {
        const campaign = window.mailingCampaignDetails?.[String(campaignId)];
        if (!campaignForm || !campaign) return;

        campaignForm.action = campaign.editAction;
        campaignForm.elements.mailing_list_id.value = String(campaign.mailingListId ?? "");
        campaignForm.elements.subject.value = campaign.subject ?? "";
        campaignForm.elements.account_code.value = campaign.accountCode ?? "general";
        campaignForm.elements.template_id.value = String(campaign.templateId ?? "");
        campaignForm.elements.html_body.value = campaign.htmlBody ?? "";
        campaignForm.elements.schedule_mode.value = campaign.schedule?.mode ?? "manual";
        campaignForm.elements.schedule_starts_at.value = campaign.schedule?.startsAt ?? "";
        campaignForm.elements.schedule_interval_value.value = campaign.schedule?.intervalValue ?? 1;
        campaignForm.elements.schedule_interval_unit.value = campaign.schedule?.intervalUnit ?? "day";
        campaignForm.elements.schedule_max_runs.value = campaign.schedule?.maxRuns ?? "";
        campaignForm.elements.schedule_ends_at.value = campaign.schedule?.endsAt ?? "";
        syncScheduleFields();
        renderCampaignAttachments(campaign.attachments);
        campaignForm.dataset.editingCampaignId = String(campaign.id);
        campaignTitle.textContent = "Modifica campagna";
        campaignHeading.textContent = `Modifica: ${campaign.subject}`;
        campaignSubmit.textContent = "Salva modifiche";
        campaignSubmit.disabled = false;
        campaignCancel.classList.remove("d-none");
        modalInstances.get("mailingCampaignModal")?.show();
    };

    const resetTemplateForm = () => {
        if (!templateForm) return;
        templateForm.reset();
        templateForm.action = templateForm.dataset.createAction;
        templateHeading.textContent = "Nuovo template";
        templateSubmit.textContent = "Salva template";
        templateSubmit.disabled = false;
        templateCancel.classList.add("d-none");
    };

    const editTemplate = (templateId) => {
        const template = window.mailingTemplateDetails?.[String(templateId)];
        if (!templateForm || !template) return;
        templateForm.action = template.editAction;
        templateForm.elements.name.value = template.name ?? "";
        templateForm.elements.subject.value = template.subject ?? "";
        templateForm.elements.html_body.value = template.htmlBody ?? "";
        templateHeading.textContent = `Modifica: ${template.name}`;
        templateSubmit.textContent = "Salva modifiche";
        templateSubmit.disabled = false;
        templateCancel.classList.remove("d-none");
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
            if (modalElement.id === "mailingTemplatesModal") {
                resetTemplateForm();
            }
        });
    });

    document.querySelectorAll("[data-mailing-open-modal]").forEach((button) => {
        button.addEventListener("click", () => {
            if (button.hasAttribute("data-mailing-new-campaign")) {
                resetCampaignForm();
            }
            const target = modalInstances.get(button.dataset.mailingOpenModal);
            const openModal = document.querySelector(".modal.show");
            if (openModal && openModal.id !== button.dataset.mailingOpenModal) {
                openModal.addEventListener("hidden.bs.modal", () => target?.show(), {once: true});
                modalInstances.get(openModal.id)?.hide();
            } else {
                target?.show();
            }
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
    scheduleMode?.addEventListener("change", syncScheduleFields);
    templateCancel?.addEventListener("click", resetTemplateForm);

    document.querySelectorAll("[data-mailing-edit-template]").forEach((button) => {
        button.addEventListener("click", () => editTemplate(button.dataset.mailingEditTemplate));
    });

    campaignForm?.elements.template_id?.addEventListener("change", (event) => {
        const template = window.mailingTemplateDetails?.[String(event.target.value)];
        if (!template || !campaignForm) return;
        campaignForm.elements.subject.value = template.subject ?? "";
        campaignForm.elements.html_body.value = template.htmlBody ?? "";
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
            : window.mailingRequestedModal === "templates"
                ? "mailingTemplatesModal"
            : null;
    if (requestedModalId) {
        modalInstances.get(requestedModalId)?.show();
    }
    syncScheduleFields();
})();

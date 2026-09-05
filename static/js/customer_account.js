(function () {
  "use strict";

  const euro = new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
  });

  function parseAmount(value) {
    const normalized = String(value || "0").trim().replace(",", ".");
    const amount = Number.parseFloat(normalized);
    return Number.isFinite(amount) ? amount : 0;
  }

  function moveModalToBody(modal) {
    if (modal && modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  }

  function fallbackCopy(text) {
    const input = document.createElement("textarea");
    input.value = text;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }

  document.addEventListener("DOMContentLoaded", function () {
    const paymentModal = document.getElementById("communicatePaymentModal");
    const claimModal = document.getElementById("contestPaymentModal");
    const onlinePaymentModal = document.getElementById("onlinePaymentModal");
    const bankTransferQrModal = document.getElementById("bankTransferQrModal");
    const bankModal = document.getElementById("bankDetailsModal");
    moveModalToBody(paymentModal);
    moveModalToBody(claimModal);
    moveModalToBody(onlinePaymentModal);
    moveModalToBody(bankTransferQrModal);
    moveModalToBody(bankModal);

    const customerFilter = document.querySelector("[data-customer-filter]");
    const customerSelect = document.querySelector("[data-customer-select]");
    if (customerFilter && customerSelect) {
      const options = Array.from(customerSelect.options).map(function (option) {
        return { option: option, text: option.text.toLocaleLowerCase("it") };
      });
      customerFilter.addEventListener("input", function () {
        const query = customerFilter.value.trim().toLocaleLowerCase("it");
        options.forEach(function (item) {
          item.option.hidden = Boolean(query) && !item.text.includes(query);
        });
      });
    }

    const invoiceCheckboxes = Array.from(document.querySelectorAll("[data-invoice-checkbox]"));
    const selectAll = document.querySelector("[data-select-all-invoices]");
    const selectionBar = document.querySelector("[data-payment-selection]");
    const selectionCount = document.querySelector("[data-selection-count]");
    const selectionTotal = document.querySelector("[data-selection-total]");
    const modalCount = document.querySelector("[data-modal-selection-count]");
    const modalTotal = document.querySelector("[data-modal-selection-total]");
    const selectedInputs = document.querySelector("[data-selected-entry-inputs]");
    const paymentFeedback = document.querySelector("[data-payment-feedback]");
    const communicateTrigger = document.querySelector("[data-communicate-payment-trigger]");
    const contestTrigger = document.querySelector("[data-contest-payment-trigger]");
    const claimCount = document.querySelector("[data-claim-selection-count]");
    const claimTotal = document.querySelector("[data-claim-selection-total]");
    const claimInputs = document.querySelector("[data-claim-entry-inputs]");
    const claimFeedback = document.querySelector("[data-claim-feedback]");
    const onlinePaymentTrigger = document.querySelector("[data-online-payment-trigger]");
    const onlinePaymentCount = document.querySelector("[data-online-payment-selection-count]");
    const onlinePaymentTotal = document.querySelector("[data-online-payment-selection-total]");
    const onlinePaymentInputs = document.querySelector("[data-online-payment-entry-inputs]");
    const onlinePaymentFeedback = document.querySelector("[data-online-payment-feedback]");
    const bankTransferTrigger = document.querySelector("[data-bank-transfer-trigger]");
    const sepaAmount = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-amount]");
    const sepaCount = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-count]");
    const sepaLoading = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-loading]");
    const sepaContent = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-content]");
    const sepaDetails = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-details]");
    const sepaQr = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-qr]");
    const sepaDownload = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-download]");
    const sepaBeneficiary = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-beneficiary]");
    const sepaIban = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-iban]");
    const sepaBic = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-bic]");
    const sepaBicRow = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-bic-row]");
    const sepaRemittance = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-remittance]");
    const sepaFeedback = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-feedback]");
    const sepaShare = bankTransferQrModal && bankTransferQrModal.querySelector("[data-share-sepa]");
    const sepaCompleted = bankTransferQrModal && bankTransferQrModal.querySelector("[data-sepa-completed]");
    const pendingActionAlert = document.querySelector("[data-pending-action-alert]");
    const pendingActionMessage = document.querySelector("[data-pending-action-message]");
    const pendingActionButtons = document.querySelector("[data-pending-action-buttons]");
    const onlinePaymentConfigured = Boolean(onlinePaymentTrigger) && !onlinePaymentTrigger.disabled;
    let sepaShareText = "";
    let sepaSelectedEntryIds = [];
    let sepaRequestNumber = 0;

    function checkedInvoices() {
      return invoiceCheckboxes.filter(function (checkbox) { return checkbox.checked; });
    }

    function updateSelection() {
      const selected = checkedInvoices();
      const total = selected.reduce(function (sum, checkbox) {
        return sum + parseAmount(checkbox.dataset.amount);
      }, 0);
      const pending = selected.filter(function (checkbox) { return Boolean(checkbox.dataset.actionStatus); });
      const hasPendingActions = pending.length > 0;
      const countLabel = selected.length + (selected.length === 1 ? " documento" : " documenti");

      if (selectionCount) selectionCount.textContent = countLabel;
      if (selectionTotal) {
        selectionTotal.textContent = euro.format(total);
        selectionTotal.classList.toggle("is-net-invalid", total <= 0);
      }
      if (modalCount) modalCount.textContent = countLabel;
      if (modalTotal) {
        modalTotal.textContent = euro.format(total);
        modalTotal.classList.toggle("is-net-invalid", total <= 0);
      }
      if (claimCount) claimCount.textContent = countLabel;
      if (claimTotal) claimTotal.textContent = euro.format(total);
      if (onlinePaymentCount) onlinePaymentCount.textContent = countLabel;
      if (onlinePaymentTotal) {
        onlinePaymentTotal.textContent = euro.format(total);
        onlinePaymentTotal.classList.toggle("is-net-invalid", total <= 0);
      }
      if (selectionBar) selectionBar.hidden = selected.length === 0;
      if (communicateTrigger) {
        communicateTrigger.disabled = selected.length === 0 || total <= 0 || hasPendingActions;
        communicateTrigger.title = hasPendingActions
          ? "Annulla o completa prima l'azione già associata ai documenti selezionati"
          : (total <= 0 ? "Il netto da bonificare deve essere maggiore di zero" : "");
      }
      if (contestTrigger) {
        contestTrigger.disabled = selected.length === 0 || hasPendingActions;
        contestTrigger.title = hasPendingActions ? "È già presente un'azione associata ai documenti selezionati" : "";
      }
      if (onlinePaymentTrigger) {
        onlinePaymentTrigger.disabled = !onlinePaymentConfigured || selected.length === 0 || total <= 0 || hasPendingActions;
        if (onlinePaymentConfigured) {
          onlinePaymentTrigger.title = hasPendingActions
            ? "Annulla o completa prima l'azione già associata ai documenti selezionati"
            : (total <= 0 ? "Il totale netto da pagare deve essere maggiore di zero" : "");
        }
      }
      if (bankTransferTrigger) {
        bankTransferTrigger.disabled = selected.length === 0 || total <= 0 || hasPendingActions;
        bankTransferTrigger.title = hasPendingActions
          ? "Annulla o completa prima l'azione già associata ai documenti selezionati"
          : (total <= 0 ? "Il netto da bonificare deve essere maggiore di zero" : "");
      }
      if (pendingActionAlert && pendingActionMessage && pendingActionButtons) {
        pendingActionAlert.hidden = !hasPendingActions;
        pendingActionButtons.replaceChildren();
        if (hasPendingActions) {
          const labels = Array.from(new Set(pending.map(function (checkbox) {
            return checkbox.dataset.actionLabel || "Azione in corso";
          })));
          const actions = new Map();
          pending.forEach(function (checkbox) {
            const url = checkbox.dataset.actionCancelUrl;
            const caseId = checkbox.dataset.actionCaseId;
            if (url && caseId && !actions.has(caseId)) actions.set(caseId, url);
          });
          pendingActionMessage.textContent = (
            pending.length === 1 ? "Il documento selezionato ha un'azione in corso: " : "Alcuni documenti selezionati hanno azioni in corso: "
          ) + labels.join(", ") + (
            actions.size
              ? ". Per avviare una nuova operazione devi prima completarla o annullarla."
              : ". Questa azione deve essere completata o verificata prima di avviare una nuova operazione."
          );
          actions.forEach(function (url) {
            const form = document.createElement("form");
            form.method = "post";
            form.action = url;
            form.addEventListener("submit", function (event) {
              if (!window.confirm("Annullare l'azione precedente e liberare i documenti associati?")) event.preventDefault();
            });
            const button = document.createElement("button");
            button.type = "submit";
            button.className = "btn btn-sm btn-outline-danger";
            button.textContent = "Annulla azione precedente";
            form.appendChild(button);
            pendingActionButtons.appendChild(form);
          });
        }
      }
      document.body.classList.toggle("customer-payment-selection-active", selected.length > 0);
      if (selectAll) {
        selectAll.checked = invoiceCheckboxes.length > 0 && selected.length === invoiceCheckboxes.length;
        selectAll.indeterminate = selected.length > 0 && selected.length < invoiceCheckboxes.length;
      }
      invoiceCheckboxes.forEach(function (checkbox) {
        const row = checkbox.closest("tr");
        if (row) row.classList.toggle("customer-invoice-selected", checkbox.checked);
      });
    }

    invoiceCheckboxes.forEach(function (checkbox) {
      checkbox.addEventListener("change", updateSelection);
      const row = checkbox.closest("tr");
      if (row) {
        row.addEventListener("click", function (event) {
          if (event.target.closest("input, button, a, label, select, textarea")) return;
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new Event("change", { bubbles: true }));
        });
      }
    });
    if (selectAll) {
      selectAll.addEventListener("change", function () {
        invoiceCheckboxes.forEach(function (checkbox) { checkbox.checked = selectAll.checked; });
        updateSelection();
      });
    }
    updateSelection();

    if (communicateTrigger && paymentModal) {
      communicateTrigger.addEventListener("click", function () {
        const selected = checkedInvoices();
        const total = selected.reduce(function (sum, checkbox) {
          return sum + parseAmount(checkbox.dataset.amount);
        }, 0);
        if (!selected.length || total <= 0) return;
        selectedInputs.replaceChildren.apply(selectedInputs, selected.map(function (checkbox) {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = "entry_ids";
          input.value = checkbox.value;
          return input;
        }));
        if (paymentFeedback) paymentFeedback.textContent = "";
        window.bootstrap.Modal.getOrCreateInstance(paymentModal).show();
      });
    }

    if (contestTrigger && claimModal) {
      contestTrigger.addEventListener("click", function () {
        const selected = checkedInvoices();
        if (!selected.length) return;
        claimInputs.replaceChildren.apply(claimInputs, selected.map(function (checkbox) {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = "entry_ids";
          input.value = checkbox.value;
          return input;
        }));
        if (claimFeedback) claimFeedback.textContent = "";
        window.bootstrap.Modal.getOrCreateInstance(claimModal).show();
      });
    }

    if (onlinePaymentTrigger && onlinePaymentModal) {
      onlinePaymentTrigger.addEventListener("click", function () {
        const selected = checkedInvoices();
        const total = selected.reduce(function (sum, checkbox) {
          return sum + parseAmount(checkbox.dataset.amount);
        }, 0);
        if (!selected.length || total <= 0 || onlinePaymentTrigger.disabled) return;
        onlinePaymentInputs.replaceChildren.apply(onlinePaymentInputs, selected.map(function (checkbox) {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = "entry_ids";
          input.value = checkbox.value;
          return input;
        }));
        if (onlinePaymentFeedback) onlinePaymentFeedback.textContent = "";
        window.bootstrap.Modal.getOrCreateInstance(onlinePaymentModal).show();
      });
    }

    async function copySepaValue(value, button, successLabel) {
      if (!value) return;
      const original = button ? button.innerHTML : "";
      try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
        else fallbackCopy(value);
        if (button) button.innerHTML = '<i class="fa-solid fa-check"></i> ' + successLabel;
        if (sepaFeedback) sepaFeedback.textContent = "Dati copiati negli appunti.";
        window.setTimeout(function () {
          if (button) button.innerHTML = original;
          if (sepaFeedback && sepaFeedback.textContent === "Dati copiati negli appunti.") sepaFeedback.textContent = "";
        }, 1800);
      } catch (_error) {
        fallbackCopy(value);
      }
    }

    if (bankTransferTrigger && bankTransferQrModal) {
      bankTransferTrigger.addEventListener("click", async function () {
        const selected = checkedInvoices();
        const total = selected.reduce(function (sum, checkbox) {
          return sum + parseAmount(checkbox.dataset.amount);
        }, 0);
        if (!selected.length || total <= 0 || bankTransferTrigger.disabled) return;

        const currentRequest = ++sepaRequestNumber;
        sepaShareText = "";
        sepaSelectedEntryIds = selected.map(function (checkbox) { return checkbox.value; });
        if (sepaAmount) sepaAmount.textContent = euro.format(total);
        if (sepaCount) sepaCount.textContent = selected.length + (selected.length === 1 ? " documento selezionato" : " documenti selezionati");
        if (sepaLoading) sepaLoading.hidden = false;
        if (sepaContent) sepaContent.hidden = true;
        if (sepaDetails) sepaDetails.hidden = true;
        if (sepaFeedback) sepaFeedback.textContent = "";
        if (sepaShare) sepaShare.hidden = true;
        if (sepaCompleted) sepaCompleted.hidden = true;
        window.bootstrap.Modal.getOrCreateInstance(bankTransferQrModal).show();

        try {
          const response = await window.fetch(bankTransferQrModal.dataset.qrUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Accept": "application/json", "Content-Type": "application/json" },
            body: JSON.stringify({
              registry_id: Number(bankTransferQrModal.dataset.registryId),
              entry_ids: selected.map(function (checkbox) { return Number(checkbox.value); }),
            }),
          });
          const result = await response.json().catch(function () { return {}; });
          if (!response.ok || !result.ok) throw new Error(result.error || "Non è stato possibile preparare il bonifico.");
          if (currentRequest !== sepaRequestNumber) return;

          if (sepaAmount) sepaAmount.textContent = euro.format(parseAmount(result.amount));
          if (sepaCount) sepaCount.textContent = result.document_count + (result.document_count === 1 ? " documento selezionato" : " documenti selezionati");
          if (sepaQr) sepaQr.src = result.qr_data_url;
          if (sepaDownload) sepaDownload.href = result.qr_data_url;
          if (sepaBeneficiary) sepaBeneficiary.textContent = result.beneficiary;
          if (sepaIban) {
            sepaIban.textContent = result.formatted_iban;
            sepaIban.dataset.copyValue = result.iban;
          }
          if (sepaBic) sepaBic.textContent = result.bic;
          if (sepaBicRow) sepaBicRow.hidden = !result.bic;
          if (sepaRemittance) {
            sepaRemittance.textContent = result.remittance;
            sepaRemittance.dataset.copyValue = result.remittance;
          }
          sepaShareText = [
            "Bonifico SEPA",
            "Beneficiario: " + result.beneficiary,
            "IBAN: " + result.formatted_iban,
            result.bic ? "BIC/SWIFT: " + result.bic : "",
            "Importo: " + euro.format(parseAmount(result.amount)),
            "Causale: " + result.remittance,
          ].filter(Boolean).join("\n");
          if (sepaLoading) sepaLoading.hidden = true;
          if (sepaContent) sepaContent.hidden = false;
          if (sepaDetails) sepaDetails.hidden = false;
          if (sepaShare) sepaShare.hidden = false;
          if (sepaCompleted) sepaCompleted.hidden = false;
        } catch (error) {
          if (currentRequest !== sepaRequestNumber) return;
          if (sepaLoading) sepaLoading.hidden = true;
          if (sepaContent) sepaContent.hidden = false;
          if (sepaFeedback) sepaFeedback.textContent = error.message || "Non è stato possibile preparare il bonifico.";
        }
      });

      bankTransferQrModal.querySelectorAll("[data-copy-sepa]").forEach(function (button) {
        button.addEventListener("click", function () {
          const key = button.dataset.copySepa;
          const source = key === "iban" ? sepaIban : sepaRemittance;
          copySepaValue(source ? (source.dataset.copyValue || source.textContent.trim()) : "", button, "Copiato");
        });
      });

      if (sepaShare) {
        sepaShare.addEventListener("click", async function () {
          if (!sepaShareText) return;
          if (navigator.share) {
            try {
              await navigator.share({ title: "Dati bonifico SEPA", text: sepaShareText });
              return;
            } catch (error) {
              if (error && error.name === "AbortError") return;
            }
          }
          await copySepaValue(sepaShareText, sepaShare, "Copiati");
        });
      }

      if (sepaCompleted && paymentModal && selectedInputs) {
        sepaCompleted.addEventListener("click", function () {
          const selected = checkedInvoices();
          if (!selected.length || !sepaSelectedEntryIds.length) return;
          selectedInputs.replaceChildren.apply(selectedInputs, sepaSelectedEntryIds.map(function (entryId) {
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = "entry_ids";
            input.value = entryId;
            return input;
          }));
          if (paymentFeedback) paymentFeedback.textContent = "";
          bankTransferQrModal.addEventListener("hidden.bs.modal", function showCommunicationModal() {
            window.bootstrap.Modal.getOrCreateInstance(paymentModal).show();
          }, { once: true });
          window.bootstrap.Modal.getOrCreateInstance(bankTransferQrModal).hide();
        });
      }
    }

    const onlinePaymentForm = document.querySelector("[data-online-payment-form]");
    if (onlinePaymentForm) {
      onlinePaymentForm.addEventListener("submit", function (event) {
        const selected = checkedInvoices();
        const total = selected.reduce(function (sum, checkbox) {
          return sum + parseAmount(checkbox.dataset.amount);
        }, 0);
        if (!selected.length || total <= 0) {
          event.preventDefault();
          if (onlinePaymentFeedback) onlinePaymentFeedback.textContent = "Seleziona documenti con un totale netto maggiore di zero.";
          return;
        }
        const submit = onlinePaymentForm.querySelector('button[type="submit"]');
        if (submit) {
          submit.disabled = true;
          submit.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Apertura pagamento…';
        }
      });
    }

    const paymentForm = document.querySelector("[data-payment-form]");
    if (paymentForm) {
      paymentForm.addEventListener("submit", function (event) {
        const selected = checkedInvoices();
        const fileInput = paymentForm.querySelector('input[type="file"]');
        const netAmount = selected.reduce(function (sum, checkbox) {
          return sum + parseAmount(checkbox.dataset.amount);
        }, 0);
        if (!selected.length || netAmount <= 0 || !fileInput || !fileInput.files.length) {
          event.preventDefault();
          if (paymentFeedback) {
            if (!selected.length) paymentFeedback.textContent = "Seleziona almeno un documento.";
            else if (netAmount <= 0) paymentFeedback.textContent = "Il netto da bonificare deve essere maggiore di zero.";
            else paymentFeedback.textContent = "Allega la contabile del bonifico.";
          }
          return;
        }
        const submit = paymentForm.querySelector('button[type="submit"]');
        if (submit) {
          submit.disabled = true;
          submit.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Invio in corso…';
        }
      });
    }

    const claimForm = document.querySelector("[data-claim-form]");
    if (claimForm) {
      claimForm.addEventListener("submit", function (event) {
        const selected = checkedInvoices();
        const reason = claimForm.querySelector('[name="reason"]')?.value.trim() || "";
        const files = Array.from(claimForm.querySelector('[name="claim_evidence"]')?.files || []);
        const totalBytes = files.reduce(function (sum, file) { return sum + file.size; }, 0);
        let error = "";
        if (!selected.length) error = "Seleziona almeno un documento.";
        else if (!reason && !files.length) error = "Scrivi una motivazione oppure allega una prova di pagamento.";
        else if (files.length > 5) error = "Puoi allegare al massimo 5 file.";
        else if (files.some(function (file) { return file.size > 12 * 1024 * 1024; })) error = "Ogni allegato può pesare al massimo 12 MB.";
        else if (totalBytes > 24 * 1024 * 1024) error = "Gli allegati possono pesare complessivamente al massimo 24 MB.";
        if (error) {
          event.preventDefault();
          if (claimFeedback) claimFeedback.textContent = error;
          return;
        }
        const submit = claimForm.querySelector('button[type="submit"]');
        if (submit) {
          submit.disabled = true;
          submit.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Invio in corso…';
        }
      });
    }

    const bankView = bankModal && bankModal.querySelector("[data-bank-view]");
    const bankFooter = bankModal && bankModal.querySelector("[data-bank-view-footer]");
    const bankEditForm = bankModal && bankModal.querySelector("[data-bank-edit-form]");
    function showBankModal(editing) {
      if (!bankModal) return;
      bankModal.classList.toggle("customer-bank-modal-editing", editing);
      if (bankView) bankView.hidden = editing;
      if (bankFooter) bankFooter.hidden = editing;
      if (bankEditForm) bankEditForm.hidden = !editing;
      window.bootstrap.Modal.getOrCreateInstance(bankModal).show();
      if (editing && bankEditForm) {
        window.setTimeout(function () {
          const firstInput = bankEditForm.querySelector("input:not([type=hidden])");
          if (firstInput) firstInput.focus();
        }, 180);
      }
    }

    document.querySelectorAll("[data-bank-details-trigger]").forEach(function (trigger) {
      trigger.addEventListener("click", function () { showBankModal(false); });
    });
    document.querySelectorAll("[data-bank-edit-trigger], [data-bank-edit-inside]").forEach(function (trigger) {
      trigger.addEventListener("click", function () { showBankModal(true); });
    });

    const copyButton = bankModal && bankModal.querySelector("[data-copy-iban]");
    if (copyButton) {
      copyButton.addEventListener("click", async function () {
        const ibanNode = bankModal.querySelector("[data-bank-iban]");
        const iban = ibanNode ? (ibanNode.dataset.bankIbanRaw || ibanNode.textContent.replace(/\s+/g, "")) : "";
        if (!iban) return;
        try {
          if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(iban);
          else fallbackCopy(iban);
          copyButton.innerHTML = '<i class="fa-solid fa-check"></i> Copiato';
          window.setTimeout(function () {
            copyButton.innerHTML = '<i class="fa-regular fa-copy"></i> Copia';
          }, 1800);
        } catch (_error) {
          fallbackCopy(iban);
        }
      });
    }
  });
})();

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
    const bankModal = document.getElementById("bankDetailsModal");
    moveModalToBody(paymentModal);
    moveModalToBody(claimModal);
    moveModalToBody(onlinePaymentModal);
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

    function checkedInvoices() {
      return invoiceCheckboxes.filter(function (checkbox) { return checkbox.checked; });
    }

    function updateSelection() {
      const selected = checkedInvoices();
      const total = selected.reduce(function (sum, checkbox) {
        return sum + parseAmount(checkbox.dataset.amount);
      }, 0);
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
        communicateTrigger.disabled = selected.length === 0 || total <= 0;
        communicateTrigger.title = total <= 0 ? "Il netto da bonificare deve essere maggiore di zero" : "";
      }
      if (contestTrigger) contestTrigger.disabled = selected.length === 0;
      if (onlinePaymentTrigger && !onlinePaymentTrigger.title) onlinePaymentTrigger.disabled = selected.length === 0 || total <= 0;
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

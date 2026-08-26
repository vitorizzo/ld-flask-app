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
    const bankModal = document.getElementById("bankDetailsModal");
    moveModalToBody(paymentModal);
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
      if (selectionBar) selectionBar.hidden = selected.length === 0;
      if (communicateTrigger) {
        communicateTrigger.disabled = selected.length === 0 || total <= 0;
        communicateTrigger.title = total <= 0 ? "Il netto da bonificare deve essere maggiore di zero" : "";
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

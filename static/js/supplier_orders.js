(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function setupArticleSearch(form) {
    const input = form.querySelector(".supplier-article-search-input");
    const codeInput = form.querySelector(".supplier-article-code");
    const results = form.querySelector(".supplier-search-results");
    const addBtn = form.querySelector(".supplier-add-article-btn");
    if (!input || !codeInput || !results || !addBtn) return;

    let timer = null;

    function clearSelection() {
      codeInput.value = "";
      addBtn.disabled = true;
    }

    function render(items) {
      results.innerHTML = "";
      if (!items.length) {
        results.classList.remove("is-open");
        return;
      }
      items.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "supplier-search-result";
        button.innerHTML = `
          <strong>${escapeHtml(item.description || item.cod_art)}</strong>
          <span>${escapeHtml(item.cod_art)}${item.root && item.root !== item.cod_art ? " · base " + escapeHtml(item.root) : ""}</span>
        `;
        button.addEventListener("click", () => {
          input.value = `${item.cod_art} - ${item.description || ""}`.trim();
          codeInput.value = item.cod_art;
          addBtn.disabled = false;
          results.innerHTML = "";
          results.classList.remove("is-open");
        });
        results.appendChild(button);
      });
      results.classList.add("is-open");
    }

    async function search() {
      const q = input.value.trim();
      clearSelection();
      if (q.length < 2) {
        render([]);
        return;
      }
      try {
        const response = await fetch(`/supplier-orders/api/articles?q=${encodeURIComponent(q)}`, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        render(payload.items || []);
      } catch (error) {
        render([]);
        results.textContent = "Ricerca prodotti non disponibile. Riprova.";
        results.classList.add("is-open", "is-error");
        console.error("Supplier article search failed", error);
      }
    }

    input.addEventListener("input", () => {
      results.classList.remove("is-error");
      window.clearTimeout(timer);
      timer = window.setTimeout(search, 220);
    });

    form.addEventListener("submit", (event) => {
      if (codeInput.value) return;
      event.preventDefault();
      input.setCustomValidity("Seleziona un prodotto dai risultati della ricerca.");
      input.reportValidity();
    });

    input.addEventListener("input", () => input.setCustomValidity(""));
  }

  function setupSilentGroupSearch() {
    const board = document.getElementById("supplierGroupsBoard");
    if (!board) return;

    let buffer = "";
    let resetTimer = null;

    function resetLater() {
      window.clearTimeout(resetTimer);
      resetTimer = window.setTimeout(() => {
        buffer = "";
      }, 900);
    }

    board.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        const active = board.querySelector(".supplier-group-link.is-key-selected");
        if (active) active.click();
        return;
      }
      if (event.key === "Backspace") {
        buffer = buffer.slice(0, -1);
      } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        buffer += event.key.toLowerCase();
      } else {
        return;
      }
      resetLater();

      const links = [...board.querySelectorAll(".supplier-group-link")];
      links.forEach((link) => link.classList.remove("is-key-selected"));
      if (!buffer) return;

      const match = links.find((link) => (link.dataset.groupName || "").startsWith(buffer));
      if (match) {
        match.classList.add("is-key-selected");
        match.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function setupSupplierModals() {
    const instances = new Map();
    document.querySelectorAll(".supplier-orders-modal").forEach((modal) => {
      if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
      }
      instances.set(`#${modal.id}`, bootstrap.Modal.getOrCreateInstance(modal));

      modal.addEventListener("show.bs.modal", () => {
        document.body.classList.add("supplier-orders-modal-open");
        modal.querySelectorAll('form:not(.supplier-article-add) button[type="submit"]').forEach((button) => {
          button.disabled = false;
        });
        modal.querySelectorAll(".supplier-add-article-btn").forEach((button) => {
          const form = button.closest(".supplier-article-add");
          button.disabled = !form?.querySelector(".supplier-article-code")?.value;
        });
      });

      modal.addEventListener("shown.bs.modal", () => {
        const requestedGroup = modal.querySelector(".supplier-manage-group[open]");
        if (requestedGroup) {
          requestedGroup.scrollIntoView({ block: "start" });
          requestedGroup.querySelector(".supplier-article-search-input")?.focus();
          return;
        }
        modal.querySelector("input:not([type='hidden']), button:not(.btn-close)")?.focus();
      });

      modal.addEventListener("hidden.bs.modal", () => {
        if (!document.querySelector(".supplier-orders-modal.show")) {
          document.body.classList.remove("supplier-orders-modal-open");
        }
        modal.querySelectorAll(".supplier-search-results.is-open").forEach((node) => {
          node.classList.remove("is-open", "is-error");
        });
        modal.querySelectorAll(".supplier-article-code").forEach((node) => {
          node.value = "";
        });
        modal.querySelectorAll(".supplier-add-article-btn").forEach((button) => {
          button.disabled = true;
        });
      });
    });

    document.querySelectorAll("[data-supplier-modal-target]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const instance = instances.get(trigger.dataset.supplierModalTarget);
        if (instance) instance.show();
      });
    });

    const requestedGroup = document.querySelector("#supplierGroupModal .supplier-manage-group[open]");
    if (requestedGroup) instances.get("#supplierGroupModal")?.show();
  }

  setupSupplierModals();
  document.querySelectorAll(".supplier-article-add").forEach(setupArticleSearch);
  setupSilentGroupSearch();

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".supplier-article-add")) {
      document.querySelectorAll(".supplier-search-results.is-open").forEach((node) => {
        node.classList.remove("is-open");
      });
    }
  });
})();

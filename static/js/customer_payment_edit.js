(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector("[data-case-edit-form]");
    if (!form) return;
    const checkboxes = Array.from(form.querySelectorAll("[data-edit-entry]"));
    const totalNode = form.querySelector("[data-edit-total]");
    const saveButton = form.querySelector("[data-save-case]");
    const requirePositive = form.dataset.requirePositive !== "0";
    const euro = new Intl.NumberFormat("it-IT", {style: "currency", currency: "EUR"});

    function update() {
      const checked = checkboxes.filter(function (item) { return item.checked; });
      const total = checked.reduce(function (sum, item) {
        const value = Number.parseFloat(String(item.dataset.amount || "0").replace(",", "."));
        return sum + (Number.isFinite(value) ? value : 0);
      }, 0);
      totalNode.textContent = euro.format(total);
      totalNode.classList.toggle("text-danger", requirePositive && total <= 0);
      saveButton.disabled = checked.length === 0 || (requirePositive && total <= 0);
      checkboxes.forEach(function (item) {
        item.closest("label")?.classList.toggle("is-selected", item.checked);
      });
    }
    checkboxes.forEach(function (item) { item.addEventListener("change", update); });
    form.addEventListener("submit", function () {
      saveButton.disabled = true;
      saveButton.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Salvataggio…';
    });
    update();
  });
})();

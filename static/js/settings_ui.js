/* Comportamento uniforme e recupero dello stato delle modali Impostazioni. */
(() => {
  function mountSettingsModals() {
    document.querySelectorAll(".settings-page-modal").forEach((modal) => {
      if (modal.parentElement !== document.body) document.body.appendChild(modal);
      const resetSubmit = () => modal.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((button) => {
        button.disabled = false;
        button.removeAttribute("aria-disabled");
        if (button.tagName === "BUTTON" && button.dataset.defaultHtml) button.innerHTML = button.dataset.defaultHtml;
      });
      if (modal.dataset.settingsModalReady === "1") return;
      modal.dataset.settingsModalReady = "1";
      modal.querySelectorAll('button[type="submit"]').forEach((button) => { button.dataset.defaultHtml = button.innerHTML; });
      modal.addEventListener("show.bs.modal", resetSubmit);
      modal.addEventListener("shown.bs.modal", resetSubmit);
      modal.addEventListener("hidden.bs.modal", resetSubmit);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountSettingsModals, { once: true });
  else mountSettingsModals();
})();

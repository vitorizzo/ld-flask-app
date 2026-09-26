document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("appQrModal");
  if (!modal) return;
  if (modal.parentElement !== document.body) document.body.appendChild(modal);
  const qrModal = window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modal) : null;
  document.querySelector("[data-app-qr-trigger]")?.addEventListener("click", (event) => {
    event.preventDefault();
    qrModal?.show();
  });
  document.querySelector("[data-copy-app-link]")?.addEventListener("click", async () => {
    const url = "https://ldapp.ldenoteca.it";
    try {
      await navigator.clipboard.writeText(url);
    } catch (err) {
      const input = document.createElement("input");
      input.value = url;
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
    }
  });
});

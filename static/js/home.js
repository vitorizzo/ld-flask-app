document.addEventListener("DOMContentLoaded", () => {
  const ua = navigator.userAgent || "";
  const dpr = Number(window.devicePixelRatio || 1);
  const lowResolutionMobile = /SM-A16/i.test(ua) ||
    (/Android/i.test(ua) && window.innerWidth <= 480 && window.screen.width <= 400 && dpr <= 3.25);
  if (lowResolutionMobile) document.body.classList.add("ld-low-resolution-mobile");
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

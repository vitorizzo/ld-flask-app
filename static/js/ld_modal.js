/* Interazione comune delle modali standard: trascinamento desktop e ridimensionamento. */
(function () {
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  function prepare(modal) {
    if (modal.dataset.ldModalReady === "1") return;
    const dialog = modal.querySelector(".modal-dialog");
    const content = modal.querySelector(".modal-content");
    const header = modal.querySelector(".modal-header");
    if (!dialog || !content || !header) return;
    modal.dataset.ldModalReady = "1";

    const resizeHandle = document.createElement("span");
    resizeHandle.className = "ld-modal-resize-handle";
    resizeHandle.setAttribute("aria-hidden", "true");
    content.appendChild(resizeHandle);

    header.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || event.target.closest("button, a, input, select, textarea")) return;
      if (window.matchMedia("(hover: none) and (pointer: coarse)").matches) return;
      const rect = dialog.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      const startLeft = rect.left;
      const startTop = rect.top;
      dialog.style.left = `${startLeft}px`;
      dialog.style.top = `${startTop}px`;
      dialog.style.transform = "none";
      header.setPointerCapture?.(event.pointerId);
      const move = (moveEvent) => {
        const left = clamp(startLeft + moveEvent.clientX - startX, 8, window.innerWidth - rect.width - 8);
        const top = clamp(startTop + moveEvent.clientY - startY, 8, window.innerHeight - rect.height - 8);
        dialog.style.left = `${left}px`;
        dialog.style.top = `${top}px`;
      };
      const stop = () => {
        header.removeEventListener("pointermove", move);
        header.removeEventListener("pointerup", stop);
        header.removeEventListener("pointercancel", stop);
      };
      header.addEventListener("pointermove", move);
      header.addEventListener("pointerup", stop);
      header.addEventListener("pointercancel", stop);
    });

    resizeHandle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || window.matchMedia("(hover: none) and (pointer: coarse)").matches) return;
      event.preventDefault();
      const rect = dialog.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      const startWidth = rect.width;
      const startHeight = rect.height;
      dialog.style.left = `${rect.left}px`;
      dialog.style.top = `${rect.top}px`;
      dialog.style.transform = "none";
      resizeHandle.setPointerCapture?.(event.pointerId);
      const move = (moveEvent) => {
        const width = clamp(startWidth + moveEvent.clientX - startX, 320, window.innerWidth - rect.left - 8);
        const height = clamp(startHeight + moveEvent.clientY - startY, 180, window.innerHeight - rect.top - 8);
        dialog.style.width = `${width}px`;
        dialog.style.maxWidth = `${width}px`;
        content.style.height = `${height}px`;
        content.style.maxHeight = `${height}px`;
      };
      const stop = () => {
        resizeHandle.removeEventListener("pointermove", move);
        resizeHandle.removeEventListener("pointerup", stop);
        resizeHandle.removeEventListener("pointercancel", stop);
      };
      resizeHandle.addEventListener("pointermove", move);
      resizeHandle.addEventListener("pointerup", stop);
      resizeHandle.addEventListener("pointercancel", stop);
    });
  }

  document.addEventListener("shown.bs.modal", (event) => {
    if (event.target.matches(".ld-modal-standard")) prepare(event.target);
  });
  document.querySelectorAll(".ld-modal-standard.show").forEach(prepare);
})();

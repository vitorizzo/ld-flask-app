(() => {
  "use strict";
  const ns = "http://www.w3.org/2000/svg";
  const money = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
  const compact = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 });

  const readData = (id) => {
    const node = document.getElementById(id);
    if (!node) return [];
    try { return JSON.parse(node.textContent || "[]"); } catch (_error) { return []; }
  };
  const svgNode = (name, attributes = {}) => {
    const node = document.createElementNS(ns, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };
  const text = (svg, value, x, y, anchor = "middle") => {
    const node = svgNode("text", { x, y, "text-anchor": anchor, class: "credit-detail-axis" });
    node.textContent = value;
    svg.appendChild(node);
  };
  const chartFrame = (svg, values, includeNegative = false) => {
    const frame = { width: 900, height: 310, left: 92, right: 28, top: 22, bottom: 58 };
    frame.plotWidth = frame.width - frame.left - frame.right;
    frame.plotHeight = frame.height - frame.top - frame.bottom;
    const rawMax = Math.max(...values, 1);
    const rawMin = includeNegative ? Math.min(...values, 0) : 0;
    const scaleMax = Math.max(Math.abs(rawMax), Math.abs(rawMin), 1);
    const magnitude = 10 ** Math.floor(Math.log10(scaleMax));
    frame.maximum = Math.ceil(rawMax / magnitude) * magnitude;
    frame.minimum = includeNegative && rawMin < 0 ? Math.floor(rawMin / magnitude) * magnitude : 0;
    const range = frame.maximum - frame.minimum;
    frame.y = (value) => frame.top + frame.plotHeight - (Number(value) - frame.minimum) / range * frame.plotHeight;
    for (let index = 0; index <= 4; index += 1) {
      const value = frame.minimum + (frame.maximum - frame.minimum) * index / 4;
      const y = frame.y(value);
      svg.appendChild(svgNode("line", { x1: frame.left, x2: frame.width - frame.right, y1: y, y2: y, class: "credit-detail-grid" }));
      text(svg, compact.format(value), frame.left - 12, y + 4, "end");
    }
    return frame;
  };

  const history = readData("customerExposureHistoryData");
  const trendSvg = document.getElementById("customerExposureTrend");
  if (trendSvg && history.length) {
    const frame = chartFrame(trendSvg, history.map((item) => Number(item.value)));
    const x = (index) => frame.left + (history.length === 1 ? frame.plotWidth / 2 : index / (history.length - 1) * frame.plotWidth);
    const coordinates = history.map((item, index) => `${x(index)},${frame.y(item.value)}`);
    if (history.length > 1) trendSvg.appendChild(svgNode("polyline", { points: coordinates.join(" "), class: "credit-detail-line" }));
    const labelStep = Math.max(1, Math.ceil(history.length / 8));
    history.forEach((item, index) => {
      const point = svgNode("circle", { cx: x(index), cy: frame.y(item.value), r: 5.5, class: "credit-detail-point" });
      const title = svgNode("title"); title.textContent = `${item.label}: ${money.format(item.value)}`; point.appendChild(title); trendSvg.appendChild(point);
      if (index % labelStep === 0 || index === history.length - 1) text(trendSvg, item.label, x(index), frame.height - 22);
    });
  }

  const aging = readData("customerAgingData");
  const agingSvg = document.getElementById("customerAgingChart");
  if (agingSvg && aging.length) {
    const frame = chartFrame(agingSvg, aging.map((item) => Number(item.value)), true);
    const slot = frame.plotWidth / aging.length;
    const baseline = frame.y(0);
    aging.forEach((item, index) => {
      const x = frame.left + index * slot + slot * 0.18;
      const y = frame.y(item.value);
      const bar = svgNode("rect", {
        x,
        y: Math.min(y, baseline),
        width: slot * 0.64,
        height: Math.max(1, Math.abs(baseline - y)),
        rx: 5,
        class: Number(item.value) < 0 ? "credit-detail-bar credit-detail-bar-negative" : "credit-detail-bar"
      });
      const title = svgNode("title"); title.textContent = `${item.label}: ${money.format(item.value)}`; bar.appendChild(title); agingSvg.appendChild(bar);
      text(agingSvg, item.label, x + slot * 0.32, frame.height - 22);
      const valueLabelY = Number(item.value) < 0 ? Math.min(frame.height - frame.bottom + 18, y + 18) : Math.max(frame.top + 14, y - 8);
      text(agingSvg, compact.format(item.value), x + slot * 0.32, valueLabelY);
    });
  }

  const communicationNode = document.getElementById("customerCreditCommunicationData");
  let communicationData = null;
  try {
    communicationData = communicationNode ? JSON.parse(communicationNode.textContent || "null") : null;
  } catch (_error) {
    communicationData = null;
  }

  const updateCommunicationModal = (modal) => {
    if (!modal || !communicationData) return;
    const channelSelect = modal.querySelector(".credit-send-channel");
    const recipientSelect = modal.querySelector(".credit-send-recipient");
    const help = modal.querySelector(".credit-send-help");
    const confirm = modal.querySelector(".credit-send-confirm");
    const selectedOption = channelSelect?.selectedOptions[0];
    const channel = channelSelect?.value || "email";
    const accountReady = selectedOption?.dataset.accountReady === "1";
    const contacts = communicationData.contacts?.[channel] || [];
    const testMode = modal.querySelector(".credit-send-test-mode")?.checked === true;
    const testEmail = modal.querySelector(".credit-send-test-email");

    if (recipientSelect) {
      const previousValue = recipientSelect.value;
      recipientSelect.innerHTML = '<option value="">Seleziona un recapito</option>';
      contacts.forEach((contact) => {
        const option = document.createElement("option");
        option.value = String(contact.id);
        option.textContent = `${contact.value}${contact.label ? ` — ${contact.label}` : ""}`;
        recipientSelect.appendChild(option);
      });
      const primary = contacts.find((contact) => contact.is_primary) || contacts[0];
      const previousStillAvailable = contacts.some((contact) => String(contact.id) === previousValue);
      if (previousStillAvailable) recipientSelect.value = previousValue;
      else if (primary) recipientSelect.value = String(primary.id);
    }

    if (help) {
      help.textContent = !accountReady
        ? `L'account ${channel === "pec" ? "PEC" : "CreditManagement"} deve ancora essere configurato.`
        : testMode
          ? "Modalità test attiva: nessun messaggio verrà inviato al cliente."
        : !contacts.length
          ? `Nessun recapito ${channel === "pec" ? "PEC" : "email"} presente nell'anagrafica cliente.`
          : `Il messaggio sarà inviato tramite l'account ${channel === "pec" ? "PEC" : "CreditManagement"}.`;
    }
    recipientSelect?.toggleAttribute("disabled", testMode);
    modal.querySelector(".credit-send-test-address")?.classList.toggle("d-none", !testMode);
    const ready = accountReady && (testMode
      ? !!testEmail?.value.trim() && testEmail.checkValidity()
      : !!recipientSelect?.value);
    const previewButton = modal.querySelector(".credit-send-preview-btn");
    if (previewButton) previewButton.disabled = !ready;
    if (confirm) confirm.disabled = false;
  };

  const resetCommunicationPreview = (modal) => {
    modal.querySelector(".credit-send-preview")?.classList.add("d-none");
    modal.querySelector(".credit-send-confirm")?.classList.add("d-none");
    modal.querySelector(".credit-send-preview-btn")?.classList.remove("d-none");
    modal.querySelector(".credit-send-feedback")?.replaceChildren();
  };

  const communicationPayload = (modal, action, button) => ({
    action,
    kind: button.dataset.kind,
    channel: modal.querySelector(".credit-send-channel")?.value || "",
    contact_id: modal.querySelector(".credit-send-recipient")?.value || "",
    test_mode: modal.querySelector(".credit-send-test-mode")?.checked === true,
    test_email: modal.querySelector(".credit-send-test-email")?.value.trim() || "",
    subject: action === "send" ? modal.querySelector(".credit-send-subject")?.value.trim() : undefined,
    html: action === "send" ? modal.querySelector(".credit-send-editor")?.innerHTML : undefined
  });

  const showCommunicationFeedback = (modal, ok, message) => {
    const alert = document.createElement("div");
    alert.className = `alert ${ok ? "alert-success" : "alert-danger"} mb-0`;
    alert.textContent = message;
    modal.querySelector(".credit-send-feedback")?.replaceChildren(alert);
  };

  document.querySelectorAll(".credit-send-modal").forEach((modal) => {
    // Le modali definite dentro page-shell restano intrappolate nel suo
    // stacking context: vanno portate nel body prima che Bootstrap le apra.
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    if (window.bootstrap?.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modal);
    }
    modal.addEventListener("show.bs.modal", () => {
      const channelSelect = modal.querySelector(".credit-send-channel");
      const readyOption = Array.from(channelSelect?.options || []).find((option) => option.dataset.accountReady === "1");
      if (readyOption) channelSelect.value = readyOption.value;
      modal.querySelector(".credit-send-test-mode").checked = false;
      modal.querySelector(".credit-send-test-email").value = "";
      const feedback = modal.querySelector(".credit-send-feedback");
      if (feedback) feedback.replaceChildren();
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });
    modal.addEventListener("hidden.bs.modal", () => {
      resetCommunicationPreview(modal);
      const active = document.activeElement;
      if (active && modal.contains(active)) active.blur();
    });
    modal.querySelector(".credit-send-channel")?.addEventListener("change", () => {
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });
    modal.querySelector(".credit-send-recipient")?.addEventListener("change", () => {
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });
    modal.querySelector(".credit-send-test-mode")?.addEventListener("change", () => {
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });
    modal.querySelector(".credit-send-test-email")?.addEventListener("input", () => {
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });

    modal.querySelector(".credit-send-preview-btn")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      const originalHtml = button.innerHTML;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Preparazione...';
      try {
        const response = await fetch(communicationData.endpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Accept": "application/json", "Content-Type": "application/json" },
          body: JSON.stringify(communicationPayload(modal, "preview", button))
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.ok) throw new Error(result.error || "Anteprima non disponibile.");
        const preview = result.preview;
        modal.querySelector("[data-preview-sender]").textContent = preview.sender || "—";
        modal.querySelector("[data-preview-recipient]").textContent = preview.recipient || "—";
        modal.querySelector("[data-preview-account]").textContent = preview.account || "—";
        modal.querySelector(".credit-send-subject").value = preview.subject || "";
        modal.querySelector(".credit-send-editor").innerHTML = preview.html || "";
        modal.querySelector(".credit-send-preview")?.classList.remove("d-none");
        modal.querySelector(".credit-send-confirm")?.classList.remove("d-none");
        button.classList.add("d-none");
      } catch (error) {
        showCommunicationFeedback(modal, false, error.message || "Errore durante la preparazione dell'anteprima.");
      } finally {
        button.innerHTML = originalHtml;
        updateCommunicationModal(modal);
      }
    });

    modal.querySelector(".credit-send-confirm")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const channel = modal.querySelector(".credit-send-channel")?.value || "";
      const contactId = modal.querySelector(".credit-send-recipient")?.value || "";
      const feedback = modal.querySelector(".credit-send-feedback");
      const testMode = modal.querySelector(".credit-send-test-mode")?.checked === true;
      if (!channel || (!testMode && !contactId) || !communicationData?.endpoint) return;

      button.disabled = true;
      let sent = false;
      const originalHtml = button.innerHTML;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Invio...';
      if (feedback) feedback.replaceChildren();
      try {
        const response = await fetch(communicationData.endpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Accept": "application/json", "Content-Type": "application/json" },
          body: JSON.stringify(communicationPayload(modal, "send", button))
        });
        const result = await response.json().catch(() => ({}));
        const alert = document.createElement("div");
        alert.className = `alert ${response.ok && result.ok ? "alert-success" : "alert-danger"} mb-0`;
        alert.textContent = result.message || result.error || "Invio non riuscito.";
        feedback?.replaceChildren(alert);
        if (response.ok && result.ok) {
          sent = true;
          return;
        }
      } catch (_error) {
        const alert = document.createElement("div");
        alert.className = "alert alert-danger mb-0";
        alert.textContent = "Errore di rete durante l'invio.";
        feedback?.replaceChildren(alert);
      } finally {
        button.innerHTML = originalHtml;
        updateCommunicationModal(modal);
        if (sent) {
          button.disabled = true;
          button.textContent = "Inviato";
        }
      }
    });
  });
})();

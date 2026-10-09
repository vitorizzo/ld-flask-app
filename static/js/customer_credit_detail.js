(() => {
  "use strict";
  const accountingStateForm = document.getElementById("customerAccountingStateForm");
  if (accountingStateForm) {
    const selectAll = accountingStateForm.querySelector("[data-credit-state-select-all]");
    const checkboxes = Array.from(accountingStateForm.querySelectorAll("[data-credit-state-checkbox]:not(:disabled)"));
    const submit = accountingStateForm.querySelector("[data-credit-state-submit]");
    const count = accountingStateForm.querySelector("[data-credit-state-count]");
    const status = accountingStateForm.querySelector("#accountingItemStatus");
    const note = accountingStateForm.querySelector("#accountingItemNote");

    const refreshSelection = () => {
      const selected = checkboxes.filter((checkbox) => checkbox.checked).length;
      if (count) count.textContent = String(selected);
      if (submit) submit.disabled = selected === 0;
      if (selectAll) {
        selectAll.checked = checkboxes.length > 0 && selected === checkboxes.length;
        selectAll.indeterminate = selected > 0 && selected < checkboxes.length;
        selectAll.disabled = checkboxes.length === 0;
      }
    };
    const refreshNoteHint = () => {
      if (!note || !status) return;
      note.placeholder = status.value === "cleared"
        ? "Es. verifica conclusa: nessuna anomalia riscontrata"
        : status.value === "under_review"
          ? "Es. contestazione ricevuta allo sportello il 07/09/2026"
          : "Es. contabile ricevuta via email il 07/09/2026";
    };

    selectAll?.addEventListener("change", () => {
      checkboxes.forEach((checkbox) => { checkbox.checked = selectAll.checked; });
      refreshSelection();
    });
    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", refreshSelection));
    status?.addEventListener("change", refreshNoteHint);
    accountingStateForm.addEventListener("submit", (event) => {
      if (!checkboxes.some((checkbox) => checkbox.checked)) {
        event.preventDefault();
        refreshSelection();
      }
    });
    refreshNoteHint();
    refreshSelection();
  }

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

  let creditTemplates = [];
  const refreshTemplateOptions = () => {
    document.querySelectorAll('.credit-send-template').forEach(select => {
      const selected = select.value;
      const kind = select.closest('.modal').querySelector('[data-kind]').dataset.kind;
      select.replaceChildren(new Option('Modello standard', ''));
      creditTemplates.filter(template => template.kind === kind).forEach(template => select.add(new Option(template.name, template.id)));
      if (Array.from(select.options).some(option => option.value === selected)) select.value = selected;
    });
  };
  const loadTemplates = async () => {
    if (!communicationData?.templatesEndpoint) return;
    const response = await fetch(communicationData.templatesEndpoint, {credentials: 'same-origin'});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'Impossibile caricare i template.');
    creditTemplates = result.templates;
    refreshTemplateOptions();
  };
  document.querySelectorAll('.credit-send-modal:not(#creditTemplateModal)').forEach(modal => {
    modal.addEventListener('show.bs.modal', () => {
      loadTemplates().catch(error => showCommunicationFeedback(modal, false, error.message));
    });
  });

  const templateModal = document.getElementById('creditTemplateModal');
  if (templateModal && communicationData?.templatesEndpoint) {
    document.body.appendChild(templateModal);
    const field = id => document.getElementById('creditTemplate' + id);
    let busy = false;
    const feedback = (ok, message) => {
      const alert = document.createElement('div');
      alert.className = `alert ${ok ? 'alert-success' : 'alert-danger'} mb-0`;
      alert.textContent = message;
      field('Feedback').replaceChildren(alert);
    };
    const setBusy = value => {
      busy = value;
      templateModal.querySelectorAll('input, textarea, select, button').forEach(node => {node.disabled = value;});
      if (!value) field('Delete').disabled = !field('List').value;
    };
    const defaultText = () => {
      const reminder = field('Kind').value === 'reminder';
      field('Subject').value = (reminder ? 'Sollecito di pagamento' : 'Estratto conto aggiornato') + ' - {{cliente}}';
      field('Body').value = 'Spett.le {{cliente}},\n\n' + (reminder ? 'Vi chiediamo cortesemente di provvedere al saldo delle partite aperte o di segnalarci eventuali difformità.' : 'Trasmettiamo la situazione contabile aggiornata.') + '\n\nSaldo attuale: {{saldo}}\n\n{{partite}}\n\nPer chiarimenti potete rispondere a questa comunicazione.\n\nCordiali saluti\nLD Enoteca';
    };
    const populate = () => {
      const template = creditTemplates.find(item => item.id === field('List').value);
      field('DeleteConfirm').classList.add('d-none');
      field('Feedback').replaceChildren();
      field('Name').value = template?.name || '';
      field('Kind').value = template?.kind || 'statement';
      if (template) { field('Subject').value = template.subject; field('Body').value = template.body; }
      else defaultText();
      field('Delete').disabled = !template;
    };
    const list = selected => {
      field('List').replaceChildren(new Option('Crea nuovo template', ''));
      creditTemplates.forEach(item => field('List').add(new Option(`${item.name} — ${item.kind === 'statement' ? 'Estratto conto' : 'Sollecito'}`, item.id)));
      field('List').value = selected || '';
      populate();
    };
    const save = async () => {
      if (busy) return;
      const data = {id: field('List').value, name: field('Name').value, kind: field('Kind').value, subject: field('Subject').value, body: field('Body').value};
      setBusy(true);
      try {
        const response = await fetch(communicationData.templatesEndpoint, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Salvataggio non riuscito.');
        const index = creditTemplates.findIndex(item => item.id === result.template.id);
        if (index < 0) creditTemplates.push(result.template); else creditTemplates[index] = result.template;
        list(result.template.id); refreshTemplateOptions(); feedback(true, 'Template salvato e disponibile nelle comunicazioni.');
      } catch (error) {feedback(false, error.message || 'Errore di rete.');}
      finally {setBusy(false);}
    };
    const remove = async () => {
      const id = field('List').value;
      if (busy || !id) return;
      setBusy(true);
      try {
        const response = await fetch(`${communicationData.templatesEndpoint}/${encodeURIComponent(id)}`, {method: 'DELETE', credentials: 'same-origin'});
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'Eliminazione non riuscita.');
        creditTemplates = creditTemplates.filter(item => item.id !== id);
        list(''); refreshTemplateOptions(); feedback(true, 'Template eliminato.');
      } catch (error) {feedback(false, error.message || 'Errore di rete.');}
      finally {setBusy(false);}
    };
    field('List').addEventListener('change', populate);
    field('Kind').addEventListener('change', () => {if (!field('List').value) defaultText();});
    let focused = field('Body');
    [field('Subject'), field('Body')].forEach(node => node.addEventListener('focus', () => {focused = node;}));
    field('Fields').addEventListener('click', event => {
      const button = event.target.closest('[data-field]');
      if (!button || busy) return;
      const target = button.dataset.field === 'partite' ? field('Body') : focused;
      target.setRangeText('{{' + button.dataset.field + '}}', target.selectionStart, target.selectionEnd, 'end');
      target.focus();
    });
    templateModal.addEventListener('show.bs.modal', () => document.body.classList.add('credit-send-modal-open'));
    templateModal.addEventListener('shown.bs.modal', async () => {
      field('Save').textContent = 'Salva template'; field('Save').onclick = save;
      field('Delete').onclick = () => field('DeleteConfirm').classList.remove('d-none');
      field('DeleteYes').onclick = remove;
      field('DeleteNo').onclick = () => field('DeleteConfirm').classList.add('d-none');
      list(''); setBusy(true);
      try {await loadTemplates(); list('');} catch (error) {feedback(false, error.message);}
      finally {setBusy(false);}
    });
    templateModal.addEventListener('hide.bs.modal', event => {if (busy) event.preventDefault();});
    templateModal.addEventListener('hidden.bs.modal', () => {
      ['Save', 'Delete', 'DeleteYes', 'DeleteNo'].forEach(id => {field(id).onclick = null;});
      document.body.classList.remove('credit-send-modal-open');
      field('Feedback').replaceChildren(); field('DeleteConfirm').classList.add('d-none');
    });
  }

  const updateCommunicationModal = (modal) => {
    if (!modal || !communicationData || modal.dataset.creditBusy === "1") return;
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
    const manualEmail = modal.querySelector(".credit-send-manual-email");

    if (recipientSelect) {
      const previousValue = recipientSelect.value;
      recipientSelect.innerHTML = '<option value="">Seleziona un recapito</option>';
      contacts.forEach((contact) => {
        const option = document.createElement("option");
        option.value = String(contact.id);
        option.textContent = `${contact.value}${contact.label ? ` — ${contact.label}` : ""}`;
        recipientSelect.appendChild(option);
      });
      const manualOption = document.createElement("option");
      manualOption.value = "__manual__";
      manualOption.textContent = "Inserisci un indirizzo manualmente";
      recipientSelect.appendChild(manualOption);
      const primary = contacts.find((contact) => contact.is_primary) || contacts[0];
      const previousStillAvailable = previousValue === "__manual__"
        || contacts.some((contact) => String(contact.id) === previousValue);
      if (previousStillAvailable) recipientSelect.value = previousValue;
      else if (primary) recipientSelect.value = String(primary.id);
      else recipientSelect.value = "__manual__";
    }

    const manualMode = recipientSelect?.value === "__manual__";

    if (help) {
      help.textContent = !accountReady
        ? `L'account ${channel === "pec" ? "PEC" : "CreditManagement"} deve ancora essere configurato.`
        : testMode
          ? "Modalità test attiva: nessun messaggio verrà inviato al cliente."
        : manualMode
          ? "Il recapito inserito verrà usato solo per questa comunicazione e mostrato nell'anteprima."
        : !contacts.length
          ? `Nessun recapito ${channel === "pec" ? "PEC" : "email"} presente nell'anagrafica cliente.`
          : `Il messaggio sarà inviato tramite l'account ${channel === "pec" ? "PEC" : "CreditManagement"}.`;
    }
    recipientSelect?.toggleAttribute("disabled", testMode);
    modal.querySelector(".credit-send-manual-address")?.classList.toggle("d-none", testMode || !manualMode);
    modal.querySelector(".credit-send-test-address")?.classList.toggle("d-none", !testMode);
    const ready = accountReady && (testMode
      ? !!testEmail?.value.trim() && testEmail.checkValidity()
      : manualMode
        ? !!manualEmail?.value.trim() && manualEmail.checkValidity()
        : !!recipientSelect?.value);
    const previewButton = modal.querySelector(".credit-send-preview-btn");
    if (previewButton) previewButton.disabled = !ready;
    if (confirm) confirm.disabled = false;
  };

  const resetCommunicationPreview = (modal) => {
    if (modal.dataset.pdfUrl) URL.revokeObjectURL(modal.dataset.pdfUrl);
    delete modal.dataset.pdfUrl;
    delete modal.dataset.pdfToken;
    modal.querySelector('.credit-send-pdf')?.removeAttribute('src');
    modal.querySelectorAll('.credit-send-pdf-link, .credit-send-pdf-download').forEach(link => link.removeAttribute('href'));
    modal.querySelector(".credit-send-preview")?.classList.add("d-none");
    modal.querySelector(".credit-send-confirm")?.classList.add("d-none");
    modal.querySelector(".credit-send-preview-btn")?.classList.remove("d-none");
    modal.querySelector(".credit-send-feedback")?.replaceChildren();
  };

  const communicationPayload = (modal, action, button) => ({
    action,
    template_id: modal.querySelector('.credit-send-template')?.value || '',
    kind: button.dataset.kind,
    channel: modal.querySelector(".credit-send-channel")?.value || "",
    contact_id: modal.querySelector(".credit-send-recipient")?.value || "",
    test_mode: modal.querySelector(".credit-send-test-mode")?.checked === true,
    test_email: modal.querySelector(".credit-send-test-email")?.value.trim() || "",
    manual_recipient: modal.querySelector(".credit-send-recipient")?.value === "__manual__",
    manual_email: modal.querySelector(".credit-send-manual-email")?.value.trim() || "",
    subject: action === "send" ? modal.querySelector(".credit-send-subject")?.value.trim() : undefined,
    pdf_token: action === 'send' ? modal.dataset.pdfToken : undefined,
    email_body: action === 'send' ? modal.querySelector('.credit-send-email-body')?.value.trim() : undefined
  });

  const showCommunicationFeedback = (modal, ok, message) => {
    const alert = document.createElement("div");
    alert.className = `alert ${ok ? "alert-success" : "alert-danger"} mb-0`;
    alert.textContent = message;
    modal.querySelector(".credit-send-feedback")?.replaceChildren(alert);
  };

  document.querySelectorAll(".credit-send-modal:not(#creditTemplateModal)").forEach((modal) => {
    // Le modali definite dentro page-shell restano intrappolate nel suo
    // stacking context: vanno portate nel body prima che Bootstrap le apra.
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    if (window.bootstrap?.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modal);
    }
    let busy = false;
    const setBusy = (value) => {
      busy = value;
      modal.dataset.creditBusy = value ? "1" : "0";
      modal.querySelectorAll("input, select, textarea").forEach(field => { field.disabled = value; });
      const editor = modal.querySelector(".credit-send-editor");
      if (editor) editor.contentEditable = value ? "false" : "true";
      if (value) modal.querySelectorAll(".credit-send-preview-btn, .credit-send-confirm").forEach(button => { button.disabled = true; });
    };
    modal.addEventListener("show.bs.modal", () => {
      document.body.classList.add("credit-send-modal-open");
      const channelSelect = modal.querySelector(".credit-send-channel");
      const readyOption = Array.from(channelSelect?.options || []).find((option) => option.dataset.accountReady === "1");
      if (readyOption) channelSelect.value = readyOption.value;
      modal.querySelector(".credit-send-test-mode").checked = false;
      modal.querySelector(".credit-send-test-email").value = "";
      modal.querySelector(".credit-send-manual-email").value = "";
      const feedback = modal.querySelector(".credit-send-feedback");
      if (feedback) feedback.replaceChildren();
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });
    modal.addEventListener("hide.bs.modal", event => { if (busy) event.preventDefault(); });
    modal.addEventListener("hidden.bs.modal", () => {
      if (!document.querySelector(".credit-send-modal.show")) document.body.classList.remove("credit-send-modal-open");
      modal.querySelector(".credit-send-preview-btn").onclick = null;
      modal.querySelector(".credit-send-confirm").onclick = null;
      resetCommunicationPreview(modal);
      const active = document.activeElement;
      if (active && modal.contains(active)) active.blur();
    });
    modal.querySelector(".credit-send-channel")?.addEventListener("change", () => {
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });
    modal.querySelector('.credit-send-template')?.addEventListener('change', () => resetCommunicationPreview(modal));
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
    modal.querySelector(".credit-send-manual-email")?.addEventListener("input", () => {
      resetCommunicationPreview(modal);
      updateCommunicationModal(modal);
    });

    const previewCommunication = async (event) => {
      if (busy || !communicationData?.endpoint) return;
      const button = event.currentTarget;
      setBusy(true);
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
        const bytes = Uint8Array.from(atob(preview.pdf_base64), char => char.charCodeAt(0));
        if (modal.dataset.pdfUrl) URL.revokeObjectURL(modal.dataset.pdfUrl);
        const pdfUrl = URL.createObjectURL(new Blob([bytes], {type: 'application/pdf'}));
        modal.dataset.pdfUrl = pdfUrl;
        modal.dataset.pdfToken = preview.pdf_token;
        modal.querySelector('.credit-send-pdf').src = pdfUrl;
        modal.querySelector('.credit-send-pdf-link').href = pdfUrl;
        const download = modal.querySelector('.credit-send-pdf-download');
        download.href = pdfUrl; download.download = preview.filename;
        modal.querySelector('.credit-send-email-body').value = preview.email_body || '';
        modal.querySelector(".credit-send-preview")?.classList.remove("d-none");
        modal.querySelector(".credit-send-confirm").textContent = "Invia ora";
        modal.querySelector(".credit-send-confirm")?.classList.remove("d-none");
        button.classList.add("d-none");
      } catch (error) {
        showCommunicationFeedback(modal, false, error.message || "Errore durante la preparazione dell'anteprima.");
      } finally {
        button.innerHTML = originalHtml;
        setBusy(false);
        updateCommunicationModal(modal);
      }
    };

    const sendCommunication = async (event) => {
      if (busy || !communicationData?.endpoint) return;
      const button = event.currentTarget;
      const channel = modal.querySelector(".credit-send-channel")?.value || "";
      const contactId = modal.querySelector(".credit-send-recipient")?.value || "";
      const feedback = modal.querySelector(".credit-send-feedback");
      const testMode = modal.querySelector(".credit-send-test-mode")?.checked === true;
      const manualMode = contactId === "__manual__";
      if (!channel || (!testMode && !manualMode && !contactId) || !communicationData?.endpoint) return;

      setBusy(true);
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
        if (response.status === 409) resetCommunicationPreview(modal);
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
        setBusy(false);
        updateCommunicationModal(modal);
        if (sent) {
          button.disabled = true;
          button.textContent = "Inviato";
        }
      }
    };
    modal.addEventListener("shown.bs.modal", () => {
      setBusy(false);
      const previewButton = modal.querySelector(".credit-send-preview-btn");
      const confirmButton = modal.querySelector(".credit-send-confirm");
      previewButton.textContent = "Mostra anteprima";
      confirmButton.textContent = "Invia ora";
      previewButton.onclick = previewCommunication;
      confirmButton.onclick = sendCommunication;
      updateCommunicationModal(modal);
    });
  });
})();

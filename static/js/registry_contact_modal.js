(() => {
  const modalEl = document.getElementById("registryContactModal");
  if (!modalEl) return;
  let modal = null;
  const saveBtn = document.getElementById("contactSaveBtn");
  const contactPickerBtn = document.getElementById("contactPickerBtn");
  const contactPickerPanel = document.getElementById("contactPickerPanel");
  const contactPickerUnavailable = document.getElementById("contactPickerUnavailable");
  const contactVcardBtn = document.getElementById("contactVcardBtn");
  const contactVcardInput = document.getElementById("contactVcardInput");
  const contactPickerSupported = Boolean(
    window.isSecureContext
    && navigator.contacts
    && typeof navigator.contacts.select === "function"
  );
  let contactPickerProperties = ["name", "tel", "email"];
  let context = null;
  let generation = 0;

  if (modalEl) {
    if (modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }
    modalEl.addEventListener("shown.bs.modal", () => {
      saveBtn.disabled = false;
      saveBtn.textContent = "Salva";
      saveBtn.onclick = saveContact;
      document.body.classList.add("registry-contact-modal-open");
    });
    modalEl.addEventListener("hidden.bs.modal", () => {
      generation++; context = null;
      saveBtn.onclick = null;
      saveBtn.disabled = false; contactPickerBtn.disabled = false; contactVcardBtn.disabled = false; contactVcardInput.value = "";
      setContactFormFeedback();
      if (!document.querySelector(".registry-contact-modal.show")) {
        document.body.classList.remove("registry-contact-modal-open");
      }
    });
    modal = new bootstrap.Modal(modalEl);
  }

  contactPickerPanel.hidden = !contactPickerSupported;
  contactPickerUnavailable.hidden = contactPickerSupported || !window.matchMedia("(hover: none), (pointer: coarse)").matches;
  if (contactPickerSupported && typeof navigator.contacts.getProperties === "function") {
    navigator.contacts.getProperties()
      .then(properties => {
        const available = ["name", "tel", "email"].filter(item => properties.includes(item));
        if (available.length) contactPickerProperties = available;
      })
      .catch(() => {});
  }

  function open(options) {
    const { registryId, contact = null } = options;
    generation++; context = options;
    saveBtn.disabled = false; contactPickerBtn.disabled = false; contactVcardBtn.disabled = false; contactVcardInput.value = "";
    document.getElementById("contactNotesGroup").hidden = options.phoneOnly === true;
    document.getElementById("contactRoleLabel").textContent = options.phoneOnly ? "Etichetta" : "Ruolo";
    document.querySelectorAll("#contactPointType option").forEach(option => { option.hidden = option.disabled = options.phoneOnly && ["email", "pec"].includes(option.value); });
    document.getElementById("registryContactModalTitle").textContent = contact ? "Modifica contatto" : "Nuovo contatto";
    document.getElementById("contactRegistryId").value = registryId;
    document.getElementById("contactId").value = contact?.id || "";
    document.getElementById("contactDisplayName").value = contact?.display_name || "";
    document.getElementById("contactRole").value = contact?.role || "";
    document.getElementById("contactNotes").value = contact?.notes || "";
    const point = (contact?.points || [])[0] || {};
    document.getElementById("contactPointType").value = point.contact_type || "phone";
    document.getElementById("contactPointValue").value = point.value || "";
    syncContactPointInput();
    setContactFormFeedback();
    modal?.show();
  }

  function setContactFormFeedback(message = "", isError = false) {
    const feedback = document.getElementById("contactFormFeedback");
    feedback.textContent = message;
    feedback.classList.toggle("is-error", isError);
  }

  function syncContactPointInput() {
    const type = document.getElementById("contactPointType").value;
    const input = document.getElementById("contactPointValue");
    const isEmail = type === "email" || type === "pec";
    input.type = isEmail ? "email" : "tel";
    input.inputMode = isEmail ? "email" : "tel";
    input.autocomplete = isEmail ? "email" : "tel";
    input.placeholder = isEmail ? "nome@dominio.it" : "Numero di telefono";
  }

  function firstSharedValue(value) {
    if (Array.isArray(value)) return String(value.find(item => String(item || "").trim()) || "").trim();
    return String(value || "").trim();
  }

  async function importContactFromVcard(file) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setContactFormFeedback("Il file vCard supera il limite di 2 MB.", true);
      return;
    }
    const session = generation;
    contactVcardBtn.disabled = true;
    setContactFormFeedback("Preparazione anteprima vCard...");
    try {
      const form = new FormData();
      form.append("file", file, file.name || "contatto.vcf");
      const registryId = document.getElementById("contactRegistryId").value;
      if (registryId) form.append("registry_id", registryId);
      const response = await fetch("/registry/api/contact-imports", {
        method: "POST",
        credentials: "same-origin",
        body: form,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Impossibile importare la vCard.");
      if (session !== generation) return;
      if (context.navigate) context.navigate(data.review_url);
      else window.location.assign(data.review_url);
    } catch (err) {
      if (session !== generation) return;
      setContactFormFeedback(err.message || "Impossibile leggere il file vCard.", true);
    } finally {
      if (session !== generation) return;
      contactVcardBtn.disabled = false;
      contactVcardInput.value = "";
    }
  }

  async function importContactFromDevice() {
    if (!contactPickerSupported) {
      setContactFormFeedback("Rubrica del dispositivo non disponibile in questo browser.", true);
      return;
    }
    const session = generation;
    contactPickerBtn.disabled = true;
    setContactFormFeedback("Apertura rubrica...");
    try {
      const selected = await navigator.contacts.select(contactPickerProperties, { multiple: false });
      if (session !== generation) return;
      const contact = Array.isArray(selected) ? selected[0] : null;
      if (!contact) {
        setContactFormFeedback();
        return;
      }
      if (context.phoneOnly && !firstSharedValue(contact.tel)) {
        setContactFormFeedback("Il contatto scelto non ha un numero di telefono condiviso.", true); return;
      }
      const name = firstSharedValue(contact.name);
      const phone = firstSharedValue(contact.tel);
      const email = firstSharedValue(contact.email);
      if (!name && !phone && !email) {
        setContactFormFeedback("Il contatto scelto non ha condiviso nome, telefono o email.", true);
        return;
      }
      if (name) document.getElementById("contactDisplayName").value = name;
      if (phone) {
        document.getElementById("contactPointType").value = "mobile";
        document.getElementById("contactPointValue").value = phone;
      } else if (email && !context.phoneOnly) {
        document.getElementById("contactPointType").value = "email";
        document.getElementById("contactPointValue").value = email;
      }
      syncContactPointInput();
      const phoneCount = Array.isArray(contact.tel) ? contact.tel.filter(Boolean).length : (phone ? 1 : 0);
      setContactFormFeedback(phoneCount > 1
        ? `Contatto importato. E' stato utilizzato il primo di ${phoneCount} numeri condivisi.`
        : "Contatto importato dalla rubrica. Controlla i dati e premi Salva.");
    } catch (err) {
      if (session !== generation) return;
      if (err && (err.name === "AbortError" || err.name === "InvalidStateError")) {
        setContactFormFeedback();
      } else {
        setContactFormFeedback(err.message || "Impossibile aprire la rubrica del dispositivo.", true);
      }
    } finally {
      if (session !== generation) return;
      contactPickerBtn.disabled = false;
    }
  }

  async function saveContact() {
    const registryId = document.getElementById("contactRegistryId").value;
    const contactId = document.getElementById("contactId").value.trim();
    const displayName = document.getElementById("contactDisplayName").value.trim();
    const role = document.getElementById("contactRole").value.trim();
    const pointType = document.getElementById("contactPointType").value;
    const pointValue = document.getElementById("contactPointValue").value.trim();
    const notes = document.getElementById("contactNotes").value.trim();
    if (!registryId) return setContactFormFeedback("Anagrafica non valida.", true);
    if (!displayName) return setContactFormFeedback("Inserisci il nome del contatto.", true);

    const payload = {
      display_name: displayName,
      role,
      notes,
      points: pointValue ? [{ contact_type: pointType, value: pointValue, is_primary: true }] : [],
    };

    if (saveBtn.disabled || !context) return;
    const session = generation;
    const activeContext = context;
    saveBtn.disabled = true;
    setContactFormFeedback("Salvataggio in corso...");
    try {
      let res;
      if (activeContext.save) {
        await activeContext.save(payload);
      } else {
      if (contactId) {
        res = await fetch(`/registry/api/contacts/${contactId}`, {
          method: "PUT",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || "Errore aggiornamento contatto");
        const linkRes = await fetch(`/registry/api/registries/${registryId}/contacts`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ contact_id: contactId, link_role: role, link_notes: notes }),
        });
        const linkData = await linkRes.json();
        if (!linkRes.ok || !linkData.ok) throw new Error(linkData.error || "Errore associazione contatto");
      } else {
        res = await fetch(`/registry/api/registries/${registryId}/contacts`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || "Errore salvataggio contatto");
      }
      }
      if (session !== generation) return;
      const onSaved = activeContext.onSaved;
      modal?.hide();
      await onSaved?.();
    } catch (err) {
      if (session !== generation) return;
      setContactFormFeedback(err.message || "Errore salvataggio", true);
    } finally {
      if (session !== generation) return;
      saveBtn.disabled = false;
    }
  }

  contactPickerBtn.addEventListener("click", importContactFromDevice);
  contactVcardBtn.addEventListener("click", () => contactVcardInput.click());
  contactVcardInput.addEventListener("change", () => importContactFromVcard(contactVcardInput.files?.[0]));
  document.getElementById("contactPointType").addEventListener("change", syncContactPointInput);
  window.LDRegistryContactModal = { open };
})();

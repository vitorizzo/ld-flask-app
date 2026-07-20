document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".customer-registry-lookup").forEach((root) => {
    const input = root.querySelector(".customer-registry-lookup-input");
    const hidden = root.querySelector('input[name="registry_id"]');
    const datalist = root.querySelector("datalist");
    if (!input || !hidden || !datalist || input.disabled) return;

    let timer = null;
    let requestNumber = 0;
    let values = new Map();
    if (root.dataset.selectedId && input.value.trim()) {
      values.set(input.value.trim(), root.dataset.selectedId);
    }

    const selectedIdFromInput = () => {
      const value = input.value.trim();
      const mappedId = values.get(value);
      if (mappedId) return mappedId;
      const idMatch = value.match(/\[ID\s+(\d+)\]\s*$/i);
      return idMatch ? idMatch[1] : "";
    };

    const selectExactValue = () => {
      hidden.value = selectedIdFromInput();
      return hidden.value;
    };

    const search = async () => {
      const term = input.value.trim();
      hidden.value = "";
      if (term.length < 2) {
        datalist.replaceChildren();
        values = new Map();
        return;
      }
      const currentRequest = ++requestNumber;
      try {
        const response = await fetch(`${root.dataset.searchUrl}?q=${encodeURIComponent(term)}`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (currentRequest !== requestNumber) return;
        values = new Map((payload.items || []).map((item) => [item.label, String(item.id)]));
        datalist.replaceChildren(...Array.from(values.keys(), (label) => {
          const option = document.createElement("option");
          option.value = label;
          return option;
        }));
        selectExactValue();
      } catch (error) {
        console.error("Ricerca anagrafiche non riuscita", error);
      }
    };

    input.addEventListener("input", () => {
      input.setCustomValidity("");
      clearTimeout(timer);
      if (selectExactValue()) {
        return;
      }
      timer = setTimeout(search, 250);
    });
    input.addEventListener("change", selectExactValue);
    root.closest("form")?.addEventListener("submit", (event) => {
      selectExactValue();
      if (!hidden.value) {
        event.preventDefault();
        input.setCustomValidity("Seleziona un cliente dai risultati della ricerca.");
        input.reportValidity();
      } else {
        input.setCustomValidity("");
      }
    });
  });
});

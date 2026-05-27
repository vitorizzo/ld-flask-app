(() => {
  const searchInput = document.getElementById("articleSearch");
  const resultsBox = document.getElementById("articleSearchResults");
  const codeInput = document.getElementById("cod_art");
  const descriptionInput = document.getElementById("display_description");
  const priceInput = document.getElementById("sale_price");

  if (!searchInput || !resultsBox || !codeInput) return;

  let timer = null;

  function hideResults() {
    resultsBox.classList.remove("is-visible");
    resultsBox.innerHTML = "";
  }

  function renderResults(items) {
    resultsBox.innerHTML = "";
    if (!items.length) {
      hideResults();
      return;
    }
    items.forEach(item => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "wine-card-search-result";
      btn.innerHTML = `<strong>${escapeHtml(item.description || item.cod_art)}</strong><small>${escapeHtml(item.cod_art || "")}</small>`;
      btn.addEventListener("click", () => {
        codeInput.value = item.cod_art || "";
        if (descriptionInput && !descriptionInput.value.trim()) descriptionInput.value = item.description || "";
        if (priceInput && item.price !== null && !priceInput.value.trim()) priceInput.value = String(item.price).replace(".", ",");
        searchInput.value = item.description || item.cod_art || "";
        hideResults();
      });
      resultsBox.appendChild(btn);
    });
    resultsBox.classList.add("is-visible");
  }

  async function searchArticles(q) {
    const res = await fetch(`/wine-cards/api/articles?q=${encodeURIComponent(q)}`, { credentials: "same-origin" });
    const data = await res.json();
    renderResults(data.articles || []);
  }

  searchInput.addEventListener("input", () => {
    const q = searchInput.value.trim();
    window.clearTimeout(timer);
    if (q.length < 2) {
      hideResults();
      return;
    }
    timer = window.setTimeout(() => searchArticles(q).catch(hideResults), 220);
  });

  document.addEventListener("click", event => {
    if (!resultsBox.contains(event.target) && event.target !== searchInput) {
      hideResults();
    }
  });

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();

(() => {
  const settingsForm = document.getElementById("wineCardSettingsForm");
  const templateSelect = document.querySelector("[data-auto-submit='settings']");
  if (!settingsForm || !templateSelect) return;

  templateSelect.addEventListener("change", () => {
    if (settingsForm.requestSubmit) {
      settingsForm.requestSubmit();
      return;
    }
    settingsForm.submit();
  });
})();

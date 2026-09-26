(function () {
  const root = document.getElementById("themePreview");
  if (!root) return;
  const form = document.querySelector(".appearance-form");
  const presetData = document.getElementById("themePresetData");
  let presets = {};
  try { presets = JSON.parse(presetData?.textContent || "{}"); } catch (_) { presets = {}; }
  const colorKeys = ["brand_primary", "brand_accent", "surface", "surface_muted", "text", "text_muted"];
  const numberKeys = ["radius", "page_padding", "base_font_size", "touch_size", "modal_width", "modal_radius"];
  function update() {
    const previewValues = {};
    colorKeys.forEach(key => { const input = form?.elements[key]; if (input?.value) previewValues[key] = input.value; });
    numberKeys.forEach(key => { const input = form?.elements[key]; if (input?.value) previewValues[key] = Number(input.value); });
    const vars = { brand_primary: "--ld-brand-primary", brand_accent: "--ld-brand-accent", surface: "--ld-surface", surface_muted: "--ld-surface-muted", text: "--ld-text", text_muted: "--ld-text-muted", radius: "--ld-radius", page_padding: "--ld-page-padding", base_font_size: "--ld-base-font-size", touch_size: "--ld-touch-size", modal_width: "--ld-modal-width", modal_radius: "--ld-modal-radius" };
    Object.entries(previewValues).forEach(([key, value]) => root.style.setProperty(vars[key], `${value}${numberKeys.includes(key) ? "px" : ""}`));
    root.querySelectorAll("[data-preview-value]").forEach(el => { const key = el.dataset.previewValue; el.textContent = `${previewValues[key] ?? ""}${numberKeys.includes(key) ? " px" : ""}`; });
  }
  form?.addEventListener("input", update);
  form?.elements.preset?.addEventListener("change", event => {
    const values = presets[event.target.value]?.values || {};
    Object.entries(values).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value; });
    update();
  });
  update();
})();

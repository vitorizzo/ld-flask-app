(function () {
  const root = document.getElementById("themePreview");
  if (!root) return;
  const form = document.querySelector(".appearance-form");
  const presetData = document.getElementById("themePresetData");
  let presets = {};
  let customThemes = {};
  try { presets = JSON.parse(presetData?.textContent || "{}"); } catch (_) { presets = {}; }
  try { customThemes = JSON.parse(document.getElementById("customThemeData")?.textContent || "{}"); } catch (_) { customThemes = {}; }
  const colorKeys = ["brand_primary", "brand_accent", "surface", "surface_muted", "text", "text_muted"];
  const numberKeys = ["radius", "page_padding", "base_font_size", "touch_size", "modal_width", "modal_radius", "divider_width", "page_max_width", "action_min_height", "action_gap", "mobile_action_columns"];
  function update() {
    const previewValues = {};
    colorKeys.forEach(key => { const input = form?.elements[key]; if (input?.value) previewValues[key] = input.value; });
    numberKeys.forEach(key => { const input = form?.elements[key]; if (input?.value) previewValues[key] = Number(input.value); });
    const vars = { brand_primary: "--ld-brand-primary", brand_accent: "--ld-brand-accent", surface: "--ld-surface", surface_muted: "--ld-surface-muted", text: "--ld-text", text_muted: "--ld-text-muted", radius: "--ld-radius", page_padding: "--ld-page-padding", base_font_size: "--ld-base-font-size", touch_size: "--ld-touch-size", modal_width: "--ld-modal-width", modal_radius: "--ld-modal-radius", divider_color: "--ld-divider-color", divider_width: "--ld-divider-width", page_max_width: "--ld-page-max-width", action_min_height: "--ld-action-min-height", action_gap: "--ld-action-gap", mobile_action_columns: "--ld-mobile-action-columns" };
    previewValues.navbar_divider_style = form?.elements.navbar_divider_style?.value || "brush";
    previewValues.footer_divider_style = form?.elements.footer_divider_style?.value || "brush";
    previewValues.divider_color = form?.elements.divider_color?.value || "#b18b77";
    Object.entries(previewValues).forEach(([key, value]) => root.style.setProperty(vars[key], `${value}${numberKeys.includes(key) ? "px" : ""}`));
    const page = root.querySelector(".theme-preview-page");
    if (page) { page.dataset.navbarDividerStyle = previewValues.navbar_divider_style; page.dataset.footerDividerStyle = previewValues.footer_divider_style; }
    root.querySelectorAll("[data-preview-value]").forEach(el => { const key = el.dataset.previewValue; el.textContent = `${previewValues[key] ?? ""}${numberKeys.includes(key) ? " px" : ""}`; });
  }
  form?.addEventListener("input", update);
  form?.elements.preset?.addEventListener("change", event => {
    const values = presets[event.target.value]?.values || {};
    Object.entries(values).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value; });
    update();
  });
  form?.elements.saved_theme?.addEventListener("change", event => {
    const values = customThemes[event.target.value];
    if (!values) return;
    Object.entries(values).forEach(([key, value]) => {
      const field = form.elements[key];
      if (!field) return;
      if (field.type === "checkbox") field.checked = Boolean(value);
      else field.value = value;
    });
    update();
  });
  update();
})();

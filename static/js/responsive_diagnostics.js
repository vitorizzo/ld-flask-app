/* Diagnostica locale, disponibile soltanto nella Home Developer su richiesta. */
(() => {
  const panel = document.getElementById('responsiveDiagnostics');
  if (!panel) return;
  const output = panel.querySelector('textarea');
  const status = panel.querySelector('[data-diagnostics-status]');
  const round = value => Math.round(value * 100) / 100;
  function measure(selector) {
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect(), css = getComputedStyle(element);
    return {
      width: round(rect.width), height: round(rect.height),
      clientWidth: element.clientWidth, scrollWidth: element.scrollWidth,
      fontSize: css.fontSize, lineHeight: css.lineHeight,
      padding: css.padding, gap: css.gap,
      scale: css.getPropertyValue('--ld-ui-scale').trim() || '1',
    };
  }
  async function collect() {
    status.textContent = 'Raccolta misure in corso...';
    let hints = {};
    try {
      hints = await Promise.race([
        navigator.userAgentData?.getHighEntropyValues(['model', 'platform']),
        new Promise(resolve => setTimeout(() => resolve({unavailable: 'timeout'}), 2000)),
      ]) || {};
    } catch (_) { /* Il browser puo' non esporre questi dati. */ }
    const root = document.documentElement, bodyCss = getComputedStyle(document.body);
    const viewport = window.visualViewport;
    output.value = JSON.stringify({
      version: document.querySelector('meta[name="ldapp-version"]')?.content,
      userAgent: navigator.userAgent, clientHints: hints,
      viewport: {innerWidth, innerHeight, rootWidth: root.clientWidth,
        visualWidth: viewport ? round(viewport.width) : null,
        visualHeight: viewport ? round(viewport.height) : null,
        visualScale: viewport?.scale ?? null},
      screen: {width: screen.width, height: screen.height, dpr: devicePixelRatio},
      input: {touchPoints: navigator.maxTouchPoints,
        coarse: matchMedia('(pointer: coarse)').matches,
        noHover: matchMedia('(hover: none)').matches},
      profile: root.dataset.responsiveProfile,
      rootInlineScale: root.style.getPropertyValue('--ld-ui-scale'),
      bodyInlineScale: document.body.style.getPropertyValue('--ld-ui-scale'),
      theme: Object.fromEntries(['base-font-size', 'mobile-font-size', 'page-padding',
        'mobile-page-padding', 'action-min-height', 'mobile-touch-size'].map(key =>
        [key, bodyCss.getPropertyValue(`--ld-${key}`).trim()])),
      elements: Object.fromEntries(['.navbar', '.navbar-brand img', '.navbar-toggler',
        '.footer', 'main.app-content', '.home-page', '.home-page h1',
        '.home-page .quick-actions', '.home-page .quick-action',
        '.home-page .quick-action i'].map(selector => [selector, measure(selector)])),
    }, null, 2);
    status.textContent = 'Misure aggiornate. Copia il rapporto per confrontare i dispositivi.';
  }
  panel.querySelector('[data-diagnostics-refresh]').addEventListener('click', collect);
  panel.querySelector('[data-diagnostics-copy]').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(output.value);
      status.textContent = 'Rapporto copiato.';
    } catch (_) {
      output.focus(); output.select();
      status.textContent = 'Rapporto selezionato: usa Copia del browser.';
    }
  });
  collect();
})();

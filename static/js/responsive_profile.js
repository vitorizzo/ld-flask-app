/* Unico criterio responsive: viewport CSS e tipo di puntatore.
   Modello e DPR non decidono le dimensioni. Caricato prima dei CSS. */
(() => {
  function apply() {
    const root = document.documentElement;
    const layoutWidth = Number(window.innerWidth || root.clientWidth || 0);
    const coarse = window.matchMedia('(pointer: coarse)').matches;
    const mobile = layoutWidth <= 820 || coarse;
    // Le fasce sono quelle della scala standard gia' usata dai telefoni corretti.
    // Zoom manuale e tastiera non cambiano il moltiplicatore.
    const scale = !mobile || layoutWidth > 820 ? 1 : layoutWidth <= 360 ? .92 : layoutWidth <= 390 ? 1 : layoutWidth <= 430 ? 1.08 : 1.12;
    const values = {
      responsiveMode: mobile ? 'mobile' : 'desktop',
      responsiveProfile: 'standard',
      responsiveViewport: String(Math.round(layoutWidth)),
      responsivePixelRatio: String(window.devicePixelRatio || 1),
    };
    for (const element of [root, document.body].filter(Boolean)) {
      Object.assign(element.dataset, values);
      element.style.setProperty('--ld-ui-scale', String(scale));
    }
  }
  apply();
  document.addEventListener('DOMContentLoaded', apply);
  let pending = false;
  window.addEventListener('resize', () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; apply(); });
  });
})();

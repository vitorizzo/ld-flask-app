/* Preserve the entire signed sheet; never apply the cheque crop to receipts. */
window.prepareIssuedCheckReceipt = async function(file) {
  const maxSide = 3200;
  const maxBytes = 800 * 1024;
  let canvas = document.createElement("canvas");
  let bitmap;
  let pdf;
  try {
    const signature = new Uint8Array(await file.slice(0, 5).arrayBuffer());
    const isPdf = String.fromCharCode(...signature) === "%PDF-";
    if (isPdf) {
      if (!window.pdfjsLib) {
        await new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
          script.onload = resolve;
          script.onerror = () => reject(new Error("Preparazione PDF non disponibile. Riprova il caricamento."));
          document.head.appendChild(script);
        });
      }
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
      pdf = await window.pdfjsLib.getDocument({data: await file.arrayBuffer()}).promise;
      if (pdf.numPages > 1 && !window.confirm("Il PDF contiene più pagine. Allegare la prima pagina completa?")) {
        throw new Error("Caricamento annullato: scegli il foglio contenente assegno e firma.");
      }
      const page = await pdf.getPage(1);
      const size = page.getViewport({scale: 1});
      const viewport = page.getViewport({scale: Math.min(3, maxSide / Math.max(size.width, size.height))});
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({canvasContext: canvas.getContext("2d", {alpha: false}), viewport, background: "white"}).promise;
    } else {
      try {
        bitmap = await createImageBitmap(file);
      } catch (_) {
        // TIFF and other formats decoded only by the existing server normalizer.
        return file;
      }
      const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext("2d", {alpha: false});
      context.fillStyle = "white";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    }
    let blob;
    for (const quality of [0.9, 0.82, 0.74, 0.66]) {
      blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
      if (!blob) throw new Error("Impossibile preparare la scansione. Il pagamento non è stato salvato.");
      if (blob.size <= maxBytes) break;
    }
    while (blob.size > maxBytes && Math.max(canvas.width, canvas.height) > 1800) {
      const reduced = document.createElement("canvas");
      reduced.width = Math.round(canvas.width * 0.9);
      reduced.height = Math.round(canvas.height * 0.9);
      reduced.getContext("2d").drawImage(canvas, 0, 0, reduced.width, reduced.height);
      canvas.width = canvas.height = 1;
      canvas = reduced;
      blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", 0.74));
      if (!blob) throw new Error("Preparazione della scansione non riuscita. Riprova.");
    }
    return new File([blob], (file.name || "ricevuta").replace(/\.[^.]+$/, "") + ".jpg", {type: "image/jpeg"});
  } finally {
    bitmap?.close();
    if (pdf) await pdf.destroy();
    canvas.width = canvas.height = 1;
  }
};

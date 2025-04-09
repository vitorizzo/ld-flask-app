// scanner.js - modulo standalone per la scansione barcode con ZXing

let codeReader;
let selectedDeviceId = null;

window.initScanner = function (buttonId, inputId, onScan = null) {
    const codeReader = new ZXing.BrowserMultiFormatReader();
    const button = document.getElementById(buttonId);

    button.addEventListener('click', () => {
        const modal = document.createElement('div');
        modal.classList.add('modal', 'fade');
        modal.setAttribute('tabindex', '-1');
        modal.innerHTML = `
          <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title">Scannerizza codice</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Chiudi"></button>
              </div>
              <div class="modal-body">
                <video id="video-preview" style="width: 100%;"></video>
              </div>
            </div>
          </div>
        `;
        document.body.appendChild(modal);

        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();

        codeReader
            .listVideoInputDevices()
            .then(videoInputDevices => {
                const videoId = videoInputDevices[0].deviceId;
                return codeReader.decodeOnceFromVideoDevice(videoId, 'video-preview');
            })
            .then(result => {
                const input = document.getElementById(inputId);
                if (input) {
                    input.value = result.text;

                    // ✨ Chiamata alla callback, se presente
                    if (typeof onScan === 'function') {
                        onScan(result.text);
                    }
                }

                bootstrapModal.hide();
                codeReader.reset();
                setTimeout(() => {
                    modal.remove();
                }, 500);
            })
            .catch(err => {
                console.error(err);
                alert('Errore durante la scansione');
                bootstrapModal.hide();
                codeReader.reset();
                setTimeout(() => {
                    modal.remove();
                }, 500);
            });
    });
};

function startScanner(inputField, deviceIdOverride = null) {
    codeReader = new ZXing.BrowserMultiFormatReader();

    codeReader.listVideoInputDevices().then(videoInputDevices => {
        codeReader.videoInputDevices = videoInputDevices;
        selectedDeviceId = deviceIdOverride || videoInputDevices[0]?.deviceId;

        const select = document.getElementById("camera-select");
        select.innerHTML = "";
        videoInputDevices.forEach(device => {
            const option = document.createElement("option");
            option.value = device.deviceId;
            option.text = device.label || `Camera ${device.deviceId}`;
            select.appendChild(option);
        });
        select.value = selectedDeviceId;

        select.onchange = () => {
            stopScanner();
            startScanner(inputField, select.value);
        };

        return codeReader.decodeFromVideoDevice(selectedDeviceId, 'barcode-video', (result, err) => {
            if (result) {
                inputField.value = result.text;
                stopScanner();
                document.getElementById("scanner-modal").style.display = "none";
            }
            if (err && !(err instanceof ZXing.NotFoundException)) {
                console.error(err);
            }
        });
    }).catch(err => {
        console.error(err);
        alert("Errore nell'avvio dello scanner");
    });
}

function stopScanner() {
    if (codeReader) {
        codeReader.reset();
    }
}

function onScanSuccess(decodedText, decodedResult) {
    const barcodeInput = document.getElementById("barcode");
    if (barcodeInput) {
        barcodeInput.value = decodedText;

        // 👉 Simula la pressione del tasto Enter
        const enterEvent = new KeyboardEvent("keydown", {
            bubbles: true,
            cancelable: true,
            key: "Enter",
            code: "Enter",
            keyCode: 13
        });
        barcodeInput.dispatchEvent(enterEvent);
    }
}

// Esponi globalmente
window.initScanner = initScanner;

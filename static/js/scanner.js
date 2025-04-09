// scanner.js - modulo standalone per la scansione barcode con ZXing

let codeReader;
let selectedDeviceId = null;

function initScanner(buttonId, inputId, onScan = null) {
    const scanButton = document.getElementById(buttonId);
    const inputField = document.getElementById(inputId);

    // Crea dinamicamente il modal solo se non esiste già
    if (!document.getElementById('scanner-modal')) {
        const modal = document.createElement('div');
        modal.id = 'scanner-modal';
        modal.style = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:1000;background:rgba(0,0,0,0.8);display:none;align-items:center;justify-content:center';

        modal.innerHTML = `
          <div style="position:relative;width:90%;max-width:600px;background:#fff;padding:10px;display:flex;flex-direction:column;align-items:center;gap:10px;">
            <div style="display:flex;justify-content:space-between;width:100%;">
              <button id="close-scanner" style="font-size:16px;">❌ Chiudi</button>
              <button id="switch-camera" style="font-size:16px;">🔄 Switch</button>
            </div>
            <video id="barcode-video" style="width:100%;height:auto;border:2px solid #00FF00;" autoplay muted playsinline></video>
            <select id="camera-select" style="width:100%;padding:5px;"></select>
            <p style="text-align:center;color:#333;margin:0;">Posiziona il codice a barre davanti alla fotocamera</p>
          </div>
        `;

        document.body.appendChild(modal);

        // Eventi dei pulsanti
        document.getElementById("close-scanner").addEventListener("click", () => {
            stopScanner();
            modal.style.display = "none";
        });

        document.getElementById("switch-camera").addEventListener("click", () => {
            if (!codeReader || !codeReader.videoInputDevices || codeReader.videoInputDevices.length < 2) return;
            const devices = codeReader.videoInputDevices;
            const currentIndex = devices.findIndex(d => d.deviceId === selectedDeviceId);
            const nextIndex = (currentIndex + 1) % devices.length;
            selectedDeviceId = devices[nextIndex].deviceId;
            stopScanner();
            startScanner(inputField, selectedDeviceId);
        });
    }

    scanButton.addEventListener("click", () => {
        startScanner(inputField, null, onScan);  // <-- aggiunto onScan
            document.getElementById("scanner-modal").style.display = "flex";
        });
    }

function startScanner(inputField, deviceIdOverride = null, onScan = null) {
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
                if (typeof onScan === 'function') {
                        onScan(result.text);
                    }
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

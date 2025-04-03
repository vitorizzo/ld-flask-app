// scanner.js - modulo standalone con UI completa e coerente

let codeReader;
let videoStream;

function initScanner(buttonId, inputId) {
    const scanButton = document.getElementById(buttonId);
    const inputField = document.getElementById(inputId);

    if (!document.getElementById('scanner-modal')) {
        // Crea la modale completa
        const modal = document.createElement('div');
        modal.id = 'scanner-modal';
        modal.style.display = 'none';
        modal.innerHTML = `
        <div class="modal" style="position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:1000;background:rgba(0,0,0,0.7);display:flex;justify-content:center;align-items:center">
            <div class="modal-content" style="position:relative;width:90%;max-width:600px;background:#fff;padding:10px;">
                <span id="close-scanner" class="close" style="position:absolute;top:10px;right:10px;font-size:30px;cursor:pointer">&times;</span>
                <button id="stopScannerBtn" style="position:absolute;top:10px;left:10px;">Ferma</button>
                <button id="switchSideBtn" style="position:absolute;top:10px;left:100px;">Switch</button>

                <div id="video-wrapper" style="position:relative;width:100%;height:calc(100% - 100px);">
                    <video id="barcode-video" style="width:100%;height:100%;object-fit:cover;" autoplay muted playsinline></video>
                    <div id="scanner-overlay" style="position:absolute;top:0;left:0;width:100%;height:100%;border:2px solid #00FF00;"></div>
                </div>

                <div id="camera-controls" style="margin-top:10px;">
                    <select id="camera-select" style="width:100%"></select>
                </div>
                <p id="scan-message" style="text-align:center;margin-top:10px">Posiziona il codice a barre all'interno del riquadro.</p>
            </div>
        </div>`;
        document.body.appendChild(modal);

        // Eventi modale
        document.getElementById("close-scanner").addEventListener("click", () => {
            stopScanner();
            modal.style.display = "none";
        });
        document.getElementById("stopScannerBtn").addEventListener("click", () => {
            stopScanner();
            modal.style.display = "none";
        });
        document.getElementById("switchSideBtn").addEventListener("click", () => {
            currentCameraMode = currentCameraMode === 'back' ? 'front' : 'back';
            updateCameraSelect();
            restartScanner(inputField);
        });
        document.getElementById("camera-select").addEventListener("change", (e) => {
            selectedCameraId = e.target.value;
            restartScanner(inputField);
        });
    }

    scanButton.addEventListener("click", () => {
        document.getElementById("scanner-modal").style.display = "flex";
        setupDevices().then(() => {
            updateCameraSelect();
            startScanner(inputField);
        });
    });
}

let videoDevices = [];
let selectedCameraId = null;
let currentCameraMode = 'back';

function setupDevices() {
    return navigator.mediaDevices.enumerateDevices().then(devices => {
        videoDevices = devices.filter(device => device.kind === 'videoinput');
        const preferred = videoDevices.find(d => d.label.toLowerCase().includes(currentCameraMode));
        selectedCameraId = preferred ? preferred.deviceId : videoDevices[0]?.deviceId;
    });
}

function updateCameraSelect() {
    const select = document.getElementById('camera-select');
    select.innerHTML = '';
    videoDevices.forEach(device => {
        const opt = document.createElement('option');
        opt.value = device.deviceId;
        opt.textContent = device.label || 'Fotocamera';
        if (device.deviceId === selectedCameraId) opt.selected = true;
        select.appendChild(opt);
    });
}

function startScanner(inputField) {
    codeReader = new ZXing.BrowserMultiFormatReader();
    codeReader.decodeFromVideoDevice(selectedCameraId, 'barcode-video', (result, err) => {
        if (result) {
            inputField.value = result.text;
            stopScanner();
            document.getElementById("scanner-modal").style.display = "none";
        }
        if (err && !(err instanceof ZXing.NotFoundException)) {
            console.error(err);
        }
    });
}

function restartScanner(inputField) {
    stopScanner();
    startScanner(inputField);
}

function stopScanner() {
    if (codeReader) codeReader.reset();
}

window.initScanner = initScanner;

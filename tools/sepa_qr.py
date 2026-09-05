import base64
import re
from decimal import Decimal, InvalidOperation


EPC_SERVICE_TAG = "BCD"
EPC_VERSION = "002"
EPC_UTF8_CHARSET = "1"
EPC_IDENTIFICATION = "SCT"


def normalize_epc_text(value, max_bytes):
    text = re.sub(r"[\r\n\t]+", " ", str(value or "")).strip()
    text = re.sub(r"\s{2,}", " ", text)
    encoded = text.encode("utf-8")[:max_bytes]
    while encoded:
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return ""


def normalize_iban(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def build_epc_payload(*, beneficiary, iban, amount, remittance, bic=None):
    beneficiary = normalize_epc_text(beneficiary, 70)
    iban = normalize_iban(iban)
    bic = normalize_epc_text(bic, 11).upper()
    remittance = normalize_epc_text(remittance, 140)
    try:
        decimal_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Importo SEPA non valido") from exc
    if not beneficiary or not iban:
        raise ValueError("Beneficiario e IBAN sono obbligatori")
    if decimal_amount <= 0 or decimal_amount > Decimal("999999999.99"):
        raise ValueError("Importo SEPA fuori dai limiti")

    # EPC069-12: riferimento strutturato vuoto e causale non strutturata.
    fields = [
        EPC_SERVICE_TAG,
        EPC_VERSION,
        EPC_UTF8_CHARSET,
        EPC_IDENTIFICATION,
        bic,
        beneficiary,
        iban,
        f"EUR{decimal_amount:.2f}",
        "",
        "",
        remittance,
        "",
    ]
    payload = "\n".join(fields)
    if len(payload.encode("utf-8")) > 331:
        raise ValueError("Dati SEPA troppo lunghi per il QR EPC")
    return payload


def epc_qr_png(payload, *, target_size=420):
    import cv2

    encoder = cv2.QRCodeEncoder_create()
    matrix = encoder.encode(payload)
    if matrix is None or not getattr(matrix, "size", 0):
        raise ValueError("Impossibile generare il QR SEPA")
    matrix = cv2.copyMakeBorder(
        matrix,
        10,
        10,
        10,
        10,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    module_size = max(1, int(target_size) // max(matrix.shape))
    matrix = cv2.resize(
        matrix,
        (matrix.shape[1] * module_size, matrix.shape[0] * module_size),
        interpolation=cv2.INTER_NEAREST,
    )
    ok, encoded = cv2.imencode(".png", matrix)
    if not ok:
        raise ValueError("Impossibile codificare il QR SEPA")
    return encoded.tobytes()


def epc_qr_data_url(payload):
    png = epc_qr_png(payload)
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

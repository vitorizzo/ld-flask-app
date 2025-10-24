import os
import logging
from datetime import datetime
from extensions import db
from models import RettificaInventario, Inventario
from tools.log_utils import get_logger

logger = get_logger("esportazioni", level=logging.DEBUG)


# --- CONFIGURAZIONE ---
# OUTPUT_FOLDER = "c:\\ldapp\\estrazioni"
OUTPUT_FOLDER = "/dati/DISCORETE/estrazioni/rettifiche_inventario"
OUTPUT_FILE = "rettifiche_inventario"

# --- PARAMETRI FISSI ---
CODICE_DITTA = "0001"
CAUSALE = "920"
RAGIONE_SOCIALE = " " * 40
NUMERO_DOC = "999"
SEZIONALE = "99"
TIPO = "0"
FLAGS = "SNNNNN"

# Deposito: 000 per shop, 400 per online — eventualmente scegli in base ai dati
DEPOSITO_NEGOZIO = "000"
DEPOSITO_ONLINE = "400"
deposito = "000"


def set_deposito(dep):
    global deposito

    if dep == "online":
        deposito = DEPOSITO_ONLINE
    deposito = DEPOSITO_NEGOZIO


# --- FUNZIONE DI FORMATTAZIONE ---
def format_field(value, length, align="left", fill=" "):
    """Ritorna un campo a larghezza fissa."""
    if value is None:
        value = ""
    s = str(value)
    if len(s) > length:
        s = s[:length]
    if align == "left":
        return s.ljust(length, fill)
    else:
        return s.rjust(length, fill)


def format_number(num, length, decimals=3):
    """
    Formatta un numero in stringa a larghezza fissa:
    - due decimali senza virgola (es. 1.00 -> '000000000100')
    - segno negativo alla fine (es. -2.00 -> '00000000200-')
    """
    if num is None:
        num = 0
    value = round(abs(float(num)) * (10 ** decimals))
    s = str(int(value)).rjust(length - 1, "0")
    if float(num) < 0:
        s = s + "-"   # segno - in ultima posizione
    else:
        s = s + "+"   # segno + finale per valori positivi
    return s


def genera_file(inventario_id):
    # --- GENERAZIONE FILE ---
    global deposito
    logger.info(f"Generazione file rettifiche inventario per inventario_id={inventario_id}, deposito={deposito_scelto}")
    deposito = Inventario.query.get(inventario_id).deposito
    inventario = Inventario.query.get(inventario_id)
    exported_file = f"{OUTPUT_FOLDER}/{OUTPUT_FILE}_{inventario.data_inventario}_{deposito}"
    os.makedirs(os.path.dirname(exported_file), exist_ok=True)

    rows = RettificaInventario.query.filter_by(inventario_id=inventario_id).all()
    logger.debug(f"Rettifiche trovate: {len(rows)}")
    if not rows:
        logger.warning(f"Nessuna rettifica trovata per inventario_id={inventario_id}. File non generato.")
        print(f"⚠️ Nessuna rettifica trovata per inventario_id={inventario_id}. File non generato.")
        return
    with open(exported_file, "w", encoding="ascii") as f:
        for idx, row in enumerate(rows, start=1):
            logging.debug(f"Elaborazione riga {idx}: {row}")
            data = inventario.data_inventario.strftime("%y%m%d")
            deposito = deposito.rjust(3, "0")
            cod_art = format_field(row.articolo_id, 20)
            quantita = format_number(row.rettifica, 12)

            # --- COMPOSIZIONE CAMPO ---
            record = (
                format_field(CODICE_DITTA, 4, "right", "0") +   # 1-4
                data +                                           # 5-10
                deposito +                                       # 11-13
                format_field(CAUSALE, 3, "right", "0") +         # 14-16
                RAGIONE_SOCIALE +                                # 17-56
                format_field(NUMERO_DOC, 6, "right", "0") +      # 57-62
                format_field(SEZIONALE, 2, "right", "0") +       # 63-64
                format_field(idx, 5, "right", "0") +             # 65-69
                cod_art +                                        # 70-89
                TIPO +                                           # 90
                quantita +                                       # 91-102
                format_number(0, 10) +                           # 103-112 (colli)
                FLAGS                                             # 113-118
            )

            f.write(record + "\n")

    logger.info(f"✅ File generato: {exported_file}")
    print(f"✅ File ASCII generato: {exported_file}")

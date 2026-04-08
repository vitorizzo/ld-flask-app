from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func
from extensions import db

# importa i modelli reali dal tuo models.py
from models import (
    CashSale, CashSalePayment,
    CashExpense, CashExpensePayment,
    PosMove, CashMove,
    CashDeposit, CashDepositCheck, CashCheck,
)

AZIENDA_CASH_FLAGS = ["*", "**"]


def _easter_sunday_gregorian(year: int) -> date:
    """
    Computus (Meeus/Jones/Butcher) per Pasqua nel calendario gregoriano.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def italian_bank_holidays(year: int) -> set[date]:
    """
    Festività nazionali (Italia) + Pasquetta.
    Nota: non include festività locali (es. Santo Patrono).
    """
    easter = _easter_sunday_gregorian(year)
    easter_monday = easter + timedelta(days=1)

    return {
        date(year, 1, 1),    # Capodanno
        date(year, 1, 6),    # Epifania
        easter_monday,       # Pasquetta
        date(year, 4, 25),   # Liberazione
        date(year, 5, 1),    # Lavoro
        date(year, 6, 2),    # Repubblica
        date(year, 8, 15),   # Ferragosto
        date(year, 11, 1),   # Ognissanti
        date(year, 12, 8),   # Immacolata
        date(year, 12, 25),  # Natale
        date(year, 12, 26),  # Santo Stefano
    }


def is_banking_day(d: date) -> bool:
    # lun=0 ... dom=6
    if d.weekday() >= 5:
        return False
    return d not in italian_bank_holidays(d.year)


def next_banking_day(d: date) -> date:
    """
    Primo giorno bancabile successivo a d.
    Esempio: venerdì -> lunedì (se non festivo).
    """
    x = d + timedelta(days=1)
    while not is_banking_day(x):
        x += timedelta(days=1)
    return x


def _d(x) -> Decimal:
    # normalizza None / numerici in Decimal
    if x is None:
        return Decimal("0.00")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _sum_amount(query) -> Decimal:
    val = query.scalar()
    return _d(val)


def calculate_closure_pure(
    cash_day_id: int,
    opening_float: Decimal,
    total_corrispettivi: Decimal,
    fondo_finale: Decimal,
    saldo_versabile_precedente: Decimal,
    saldo_movimenti_cassa: Decimal,
    incasso_consegnato: Decimal,
    tolleranza: Decimal = Decimal("2.00"),
):
    opening_float = _d(opening_float)
    total_corrispettivi = _d(total_corrispettivi)
    fondo_finale = _d(fondo_finale)
    saldo_versabile_precedente = _d(saldo_versabile_precedente)
    saldo_movimenti_cassa = _d(saldo_movimenti_cassa)
    incasso_consegnato = _d(incasso_consegnato)
    tolleranza = _d(tolleranza)

    delta_fondo = fondo_finale - opening_float

    has_fondo_iniziale = opening_float > Decimal("0")
    has_fondo_finale = fondo_finale > Decimal("0")
    has_corrispettivi = total_corrispettivi > Decimal("0")

    # =========================
    # INCASSI - DETTAGLIO
    # =========================
    incassi_cash_solo = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.direction == "in",
            CashSalePayment.method == "cash",
            CashSalePayment.off_cash.is_(False),
            CashSalePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    incassi_fuori_cassa = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.direction == "in",
            CashSalePayment.method == "cash",
            CashSalePayment.off_cash.is_(True),
            CashSalePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    incassi_pos = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.direction == "in",
            CashSalePayment.method == "pos",
            CashSalePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    incassi_bank = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.direction == "in",
            CashSalePayment.method == "bank",
            CashSalePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    incassi_check = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.direction == "in",
            CashSalePayment.method == "check",
            CashSalePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    incassi_azienda_giorno = (
        incassi_cash_solo
        + incassi_fuori_cassa
        + incassi_pos
        + incassi_bank
        + incassi_check
    )

    # chiave legacy
    incassi_cash = incassi_azienda_giorno

    incassi_azienda_lordi = incassi_azienda_giorno + total_corrispettivi

    totale_incassi_fisici = incassi_cash_solo + incassi_check + total_corrispettivi
    totale_incassi_elettronici = incassi_pos + incassi_bank
    totale_incassi_fuori_cassa = incassi_fuori_cassa

    # =========================
    # SPESE - DETTAGLIO
    # =========================
    spese_cash_solo = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashExpensePayment.amount), 0))
        .join(CashExpense, CashExpense.id == CashExpensePayment.expense_id)
        .filter(
            CashExpense.cash_day_id == cash_day_id,
            CashExpensePayment.direction == "out",
            CashExpensePayment.method == "cash",
            CashExpensePayment.off_cash.is_(False),
            CashExpensePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    spese_fuori_cassa = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashExpensePayment.amount), 0))
        .join(CashExpense, CashExpense.id == CashExpensePayment.expense_id)
        .filter(
            CashExpense.cash_day_id == cash_day_id,
            CashExpensePayment.direction == "out",
            CashExpensePayment.method == "cash",
            CashExpensePayment.off_cash.is_(True),
            CashExpensePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    spese_pos = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashExpensePayment.amount), 0))
        .join(CashExpense, CashExpense.id == CashExpensePayment.expense_id)
        .filter(
            CashExpense.cash_day_id == cash_day_id,
            CashExpensePayment.direction == "out",
            CashExpensePayment.method == "pos",
            CashExpensePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    spese_bank = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashExpensePayment.amount), 0))
        .join(CashExpense, CashExpense.id == CashExpensePayment.expense_id)
        .filter(
            CashExpense.cash_day_id == cash_day_id,
            CashExpensePayment.direction == "out",
            CashExpensePayment.method == "bank",
            CashExpensePayment.flag.in_(AZIENDA_CASH_FLAGS),
        )
    )

    totale_spese_fisiche = spese_cash_solo
    totale_spese_elettroniche = spese_pos + spese_bank
    totale_spese_fuori_cassa = spese_fuori_cassa

    # chiave legacy
    spese_cash = spese_cash_solo

    # =========================
    # POS MOVES
    # =========================
    totale_pos = _sum_amount(
        db.session.query(func.coalesce(func.sum(PosMove.amount), 0))
        .filter(
            PosMove.cash_day_id == cash_day_id,
            PosMove.direction == "in",
        )
    ) - _sum_amount(
        db.session.query(func.coalesce(func.sum(PosMove.amount), 0))
        .filter(
            PosMove.cash_day_id == cash_day_id,
            PosMove.direction == "out",
        )
    )

    # =========================
    # SPICCI
    # =========================
    spicci_prelievi = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashMove.amount), 0))
        .filter(
            CashMove.cash_day_id == cash_day_id,
            CashMove.kind == "spicci",
            CashMove.direction == "out",
        )
    )

    spicci_versamenti = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashMove.amount), 0))
        .filter(
            CashMove.cash_day_id == cash_day_id,
            CashMove.kind == "spicci",
            CashMove.direction == "in",
        )
    )

    saldo_spicci = spicci_versamenti - spicci_prelievi

    # =========================
    # CONTANTI FISICI / CASSETTO
    # I POS stanno qui come rettifica unica
    # =========================
    contanti_fisici = (
        incassi_azienda_lordi
        - totale_pos
        - spese_cash_solo
        + saldo_movimenti_cassa
    )

    # =========================
    # ASSEGNI
    # =========================
    assegni_odierni = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.method == "check",
            CashSalePayment.direction == "in",
            CashSalePayment.flag == "*",
        )
    )

    assegni_postdatati = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.method == "check",
            CashSalePayment.direction == "in",
            CashSalePayment.flag == "**",
        )
    )

    # =========================
    # VERSAMENTI
    # =========================
    depositi_cash_oggi = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashDeposit.cash_amount), 0))
        .filter(CashDeposit.cash_day_id == cash_day_id)
    )

    depositi_assegni_oggi = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .join(CashDepositCheck, CashDepositCheck.check_id == CashCheck.id)
        .join(CashDeposit, CashDeposit.id == CashDepositCheck.deposit_id)
        .filter(CashDeposit.cash_day_id == cash_day_id)
    )

    totale_versato_oggi = depositi_cash_oggi + depositi_assegni_oggi

    depositi_intermedi_cash = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashDeposit.cash_amount), 0))
        .filter(
            CashDeposit.cash_day_id == cash_day_id,
            CashDeposit.deposit_type == "versamento_intermedio",
        )
    )

    depositi_intermedi_assegni = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .join(CashDepositCheck, CashDepositCheck.check_id == CashCheck.id)
        .join(CashDeposit, CashDeposit.id == CashDepositCheck.deposit_id)
        .filter(
            CashDeposit.cash_day_id == cash_day_id,
            CashDeposit.deposit_type == "versamento_intermedio",
        )
    )

    totale_versato_intermedio = depositi_intermedi_cash + depositi_intermedi_assegni

    depositi_incasso_cash = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashDeposit.cash_amount), 0))
        .filter(
            CashDeposit.cash_day_id == cash_day_id,
            CashDeposit.deposit_type == "versamento_incasso",
        )
    )

    depositi_incasso_assegni = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .join(CashDepositCheck, CashDepositCheck.check_id == CashCheck.id)
        .join(CashDeposit, CashDeposit.id == CashDepositCheck.deposit_id)
        .filter(
            CashDeposit.cash_day_id == cash_day_id,
            CashDeposit.deposit_type == "versamento_incasso",
        )
    )

    totale_versato_incasso = depositi_incasso_cash + depositi_incasso_assegni

    assegni_in_pancia = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .filter(CashCheck.status.in_(["received", "moved"]))
    )

    # =========================
    # VERSABILE
    # =========================
    versabile_giornata = contanti_fisici + assegni_odierni

    massimo_contanti_incasso = saldo_versabile_precedente - assegni_in_pancia
    if massimo_contanti_incasso < Decimal("0.00"):
        massimo_contanti_incasso = Decimal("0.00")

    debito_contanti_incasso = depositi_incasso_cash - massimo_contanti_incasso
    if debito_contanti_incasso < Decimal("0.00"):
        debito_contanti_incasso = Decimal("0.00")

    saldo_attuale = (
        saldo_versabile_precedente
        + versabile_giornata
        + assegni_postdatati
        - totale_versato_oggi
    )

    saldo_versabile = saldo_attuale
    versabile_residuo = versabile_giornata - totale_versato_intermedio - debito_contanti_incasso

    # =========================
    # QUADRATURA
    # =========================
    incasso_calcolato = contanti_fisici - delta_fondo
    valore_atteso_cassetto = incasso_calcolato
    delta_quadratura = incasso_consegnato - valore_atteso_cassetto
    anomalia = abs(delta_quadratura) > tolleranza

    totale_giornata_is_partial = not (
        has_corrispettivi and has_fondo_iniziale and has_fondo_finale
    )

    return {
        "fondo_iniziale": opening_float,
        "fondo_finale": fondo_finale,
        "delta_fondo": delta_fondo,

        "incassi_cash": incassi_cash,
        "incassi_azienda_lordi": incassi_azienda_lordi,
        "incassi_cash_solo": incassi_cash_solo,
        "incassi_fuori_cassa": incassi_fuori_cassa,
        "incassi_pos": incassi_pos,
        "incassi_bank": incassi_bank,
        "incassi_check": incassi_check,
        "totale_incassi_fisici": totale_incassi_fisici,
        "totale_incassi_elettronici": totale_incassi_elettronici,
        "totale_incassi_fuori_cassa": totale_incassi_fuori_cassa,

        "spese_cash": spese_cash,
        "spese_cash_solo": spese_cash_solo,
        "spese_fuori_cassa": spese_fuori_cassa,
        "spese_pos": spese_pos,
        "spese_bank": spese_bank,
        "totale_spese_fisiche": totale_spese_fisiche,
        "totale_spese_elettroniche": totale_spese_elettroniche,
        "totale_spese_fuori_cassa": totale_spese_fuori_cassa,

        "spicci_prelievi": spicci_prelievi,
        "spicci_versamenti": spicci_versamenti,
        "saldo_spicci": saldo_spicci,

        "contanti_fisici": contanti_fisici,
        "totale_pos": totale_pos,

        "assegni_odierni": assegni_odierni,
        "assegni_postdatati": assegni_postdatati,

        "incasso_calcolato": incasso_calcolato,
        "incasso_consegnato": incasso_consegnato,
        "saldo_movimenti_cassa": saldo_movimenti_cassa,
        "valore_atteso_cassetto": valore_atteso_cassetto,
        "delta_quadratura": delta_quadratura,
        "anomalia": anomalia,

        "versabile_giornata": versabile_giornata,
        "versabile_residuo": versabile_residuo,

        "depositi_cash_oggi": depositi_cash_oggi,
        "depositi_assegni_oggi": depositi_assegni_oggi,
        "totale_versato_oggi": totale_versato_oggi,

        "depositi_intermedi_cash": depositi_intermedi_cash,
        "depositi_intermedi_assegni": depositi_intermedi_assegni,
        "totale_versato_intermedio": totale_versato_intermedio,

        "depositi_incasso_cash": depositi_incasso_cash,
        "depositi_incasso_assegni": depositi_incasso_assegni,
        "totale_versato_incasso": totale_versato_incasso,

        "saldo_versabile": saldo_versabile,

        "assegni_in_pancia": assegni_in_pancia,
        "saldo_attuale": saldo_attuale,
        "massimo_contanti_incasso": massimo_contanti_incasso,
        "debito_contanti_incasso": debito_contanti_incasso,

        "has_corrispettivi": has_corrispettivi,
        "has_fondo_iniziale": has_fondo_iniziale,
        "has_fondo_finale": has_fondo_finale,
        "totale_giornata_is_partial": totale_giornata_is_partial,

        "note": "Report diagnostico esteso: incassi/spese distinti per metodo, spicci separati, POS rettificati nel cassetto atteso.",
    }

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func
from extensions import db

# importa i modelli reali dal tuo models.py
from models import (
    CashSale, CashSalePayment,
    CashExpense, CashExpensePayment,
    PosMove,
    CashDeposit, CashDepositCheck, CashCheck,
)


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

# aggiungi ai modelli importati
def calculate_closure_pure(
    cash_day_id: int,
    opening_float: Decimal,
    total_corrispettivi: Decimal,
    fondo_finale: Decimal,
    saldo_versabile_precedente: Decimal,
    incasso_consegnato: Decimal,
    tolleranza: Decimal = Decimal("2.00"),
):
    """
    Calcolo chiusura giornaliera (solo DB aziendale).

    NOTE (allineate ai tuoi esempi):
    - Q = contanti_fisici + assegni_odierni (*)   [incassi odierni versabili]
    - S_new = S_prev + Q + assegni_postdatati (**) - totale_versato_oggi
    - Q_residua = Q - versamenti_intermedi_oggi  (cash + assegni nei deposit_type='versamento_intermedio')
    - incasso_consegnato != totale_versato (restano separati)
    """
    opening_float = _d(opening_float)
    total_corrispettivi = _d(total_corrispettivi)
    fondo_finale = _d(fondo_finale)
    saldo_versabile_precedente = _d(saldo_versabile_precedente)
    incasso_consegnato = _d(incasso_consegnato)
    tolleranza = _d(tolleranza)

    delta_fondo = fondo_finale - opening_float

    # =========================
    # CONTANTI: incassi cash
    # =========================
    incassi_cash = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashSalePayment.amount), 0))
        .join(CashSale, CashSale.id == CashSalePayment.sale_id)
        .filter(
            CashSale.cash_day_id == cash_day_id,
            CashSalePayment.method == "cash",
            CashSalePayment.direction == "in",
        )
    )

    # =========================
    # CONTANTI: spese cash
    # =========================
    spese_cash = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashExpensePayment.amount), 0))
        .join(CashExpense, CashExpense.id == CashExpensePayment.expense_id)
        .filter(
            CashExpense.cash_day_id == cash_day_id,
            CashExpensePayment.method == "cash",
            CashExpensePayment.direction == "out",
        )
    )

    # =========================
    # POS
    # =========================
    totale_pos = _sum_amount(
        db.session.query(func.coalesce(func.sum(PosMove.amount), 0))
        .filter(PosMove.cash_day_id == cash_day_id, PosMove.direction == "in")
    ) - _sum_amount(
        db.session.query(func.coalesce(func.sum(PosMove.amount), 0))
        .filter(PosMove.cash_day_id == cash_day_id, PosMove.direction == "out")
    )

    contanti_fisici = incassi_cash - spese_cash - totale_pos

    # =========================
    # ASSEGNI: odierni (*) e postdatati (**)
    # (flag sul pagamento, come da tua regola)
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
    # VERSAMENTI (cash_deposits + tabella ponte assegni)
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

    # solo versamenti intermedi (per Q residua)
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

    # =========================
    # ASSEGNI ANCORA IN PANCIA
    # solo assegni realmente detenuti
    # =========================
    assegni_in_pancia = _sum_amount(
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .filter(CashCheck.status.in_(["received", "moved"]))
    )

    # =========================
    # SALDO ATTUALE E DEBITO CONTANTI DA VERSAMENTO INCASSO
    # =========================
    saldo_attuale = saldo_versabile_precedente + versabile_giornata + assegni_postdatati - totale_versato_oggi

    massimo_contanti_incasso = saldo_attuale - assegni_in_pancia

    debito_contanti_incasso = Decimal("0.00")
    if massimo_contanti_incasso < 0:
        debito_contanti_incasso = -massimo_contanti_incasso

    # =========================
    # FORMULE
    # =========================
    incasso_calcolato = contanti_fisici + total_corrispettivi - delta_fondo

    # Q (incasso odierno versabile)
    versabile_giornata = contanti_fisici + assegni_odierni

    # S (saldo “in pancia” a fine giornata)
    saldo_versabile = saldo_attuale

    # Q residua:
    # - tolgo i versamenti intermedi del giorno
    # - tolgo l'eventuale debito contanti generato da versamenti incasso oltre soglia
    versabile_residuo = versabile_giornata - totale_versato_intermedio - debito_contanti_incasso

    delta_quadratura = incasso_consegnato - incasso_calcolato
    anomalia = abs(delta_quadratura) > tolleranza

    return {
        "fondo_iniziale": opening_float,
        "fondo_finale": fondo_finale,
        "delta_fondo": delta_fondo,

        "incassi_cash": incassi_cash,
        "spese_cash": spese_cash,
        "contanti_fisici": contanti_fisici,

        "totale_pos": totale_pos,

        "assegni_odierni": assegni_odierni,
        "assegni_postdatati": assegni_postdatati,

        "incasso_calcolato": incasso_calcolato,
        "incasso_consegnato": incasso_consegnato,
        "delta_quadratura": delta_quadratura,
        "anomalia": anomalia,

        "versabile_giornata": versabile_giornata,
        "versabile_residuo": versabile_residuo,

        "depositi_cash_oggi": depositi_cash_oggi,
        "depositi_assegni_oggi": depositi_assegni_oggi,
        "totale_versato_oggi": totale_versato_oggi,
        "totale_versato_intermedio": totale_versato_intermedio,

        "saldo_versabile": saldo_versabile,

        "assegni_in_pancia": assegni_in_pancia,
        "saldo_attuale": saldo_attuale,
        "massimo_contanti_incasso": massimo_contanti_incasso,
        "debito_contanti_incasso": debito_contanti_incasso,

        "note": "Calcolo DB + versamenti (CashDeposit). Flag +/x ignorati qui.",
    }

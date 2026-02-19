from decimal import Decimal
from sqlalchemy import func
from extensions import db

# importa i modelli reali dal tuo models.py
from models import (
    CashSale, CashSalePayment,
    CashExpense, CashExpensePayment,
    PosMove,
)

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
    incasso_consegnato: Decimal,
    tolleranza: Decimal = Decimal("2.00"),
):
    """
    Calcolo chiusura giornaliera (solo DB aziendale).
    Approccio stabile: solo query pure, nessuna relationship, nessun eager loading.

    Note:
    - contanti_fisici = incassi cash - spese cash (del giorno)
    - totale_pos = somma pos_moves (in)
    - assegni_odierni = somma pagamenti method='check' flag='*'
    - assegni_postdatati = somma pagamenti method='check' flag='**'
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

    contanti_fisici = incassi_cash - spese_cash

    # =========================
    # POS: movimenti pos_moves
    # =========================
    totale_pos = _sum_amount(
        db.session.query(func.coalesce(func.sum(PosMove.amount), 0))
        .filter(
            PosMove.cash_day_id == cash_day_id,
            PosMove.direction == "in",
        )
    )

    # =========================
    # ASSEGNI: odierni (*) e postdatati (**)
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
    # FORMULE
    # =========================
    # IC = Contanti_fisici + Totale_corrispettivi − Totale_POS_device - ΔFondo
    incasso_calcolato = contanti_fisici + total_corrispettivi - totale_pos - delta_fondo

    # Q = Contanti_fisici + Assegni_odierni (*)
    versabile_giornata = contanti_fisici + assegni_odierni

    # S_new = S_prev + Q + Assegni_postdatati (**)
    saldo_versabile = saldo_versabile_precedente + versabile_giornata + assegni_postdatati

    # Quadratura
    delta_quadratura = incasso_calcolato - incasso_consegnato
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
        "saldo_versabile": saldo_versabile,
        "note": "Calcolo solo DB aziendale (flag +/x ignorati qui).",
    }

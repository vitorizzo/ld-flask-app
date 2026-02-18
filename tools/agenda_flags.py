# /tools/agenda_flags.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional


ALLOWED_FLAGS = {"*", "**", "+", "x", "#", "!"}
ALLOWED_DIRECTIONS = {"in", "out"}


def _to_decimal(x: Any) -> Decimal:
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid amount: {x!r}")


@dataclass(frozen=True)
class AgendaDeltas:
    # Totale fisico "in cassetto" (include anche assegni se sono in cassa)
    cash_delta: Decimal

    # Quota versabile (quanto matura oggi per essere versato "domani")
    q_versabile_delta: Decimal

    # Saldo versabile (saldo complessivo aziendale versabile, indipendente da quando)
    s_versabile_delta: Decimal

    # Breakdown facoltativo (per UI “dettaglio versabile”)
    drawer_cash_delta: Decimal          # contante fisico nel cassetto
    drawer_checks_delta: Decimal        # assegni fisici nel cassetto
    q_cash_delta: Decimal               # quota versabile contanti
    q_checks_delta: Decimal             # quota versabile assegni (maturi)
    s_cash_delta: Decimal               # saldo versabile contanti
    s_checks_delta: Decimal             # saldo versabile assegni (totale)


def compute_agenda_deltas(
    *,
    flag: str,
    direction: str,
    amount: Any,
    off_cash: bool = False,
    method: str = "cash",
    # assegni: per decidere se entrano nel "versabile odierno" (Q)
    check_mature: bool = False,
    check_in_cash: bool = True,
) -> AgendaDeltas:
    """
    Calcola i delta per un singolo movimento.

    - flag: '*', '**', '+', 'x', '#', '!'
    - direction: 'in' oppure 'out'
    - amount: numero/Decimal, sempre positivo (il segno lo applichiamo noi)
    - off_cash: True se non è fisicamente nel cassetto (es. incasso fuori ufficio)
    - method: 'cash' | 'pos' | 'bank' | 'other' | 'check' (valori liberi, ma 'check' ha logica dedicata)
    - check_mature: per method='check', se è maturato (scadenza <= oggi)
    - check_in_cash: per method='check', se è fisicamente in cassa (non versato / non consegnato altrove)
    """

    if flag not in ALLOWED_FLAGS:
        raise ValueError(f"Invalid flag: {flag!r}")
    if direction not in ALLOWED_DIRECTIONS:
        raise ValueError(f"Invalid direction: {direction!r}")

    amt = _to_decimal(amount)
    if amt < 0:
        raise ValueError("amount must be >= 0")

    sign = Decimal("1") if direction == "in" else Decimal("-1")
    signed = amt * sign

    # Base: tutto a zero
    cash_delta = Decimal("0")
    qv = Decimal("0")
    sv = Decimal("0")

    drawer_cash = Decimal("0")
    drawer_checks = Decimal("0")
    q_cash = Decimal("0")
    q_checks = Decimal("0")
    s_cash = Decimal("0")
    s_checks = Decimal("0")

    is_check = (method == "check")

    # -------------------------
    # 1) Regole per flag (senza considerare ancora 'off_cash' sul cash_delta)
    # -------------------------

    # '#' non contribuisce a nessun contatore (è “tracciamento” aziendale fuori contatori)
    if flag == "#":
        return AgendaDeltas(
            cash_delta=Decimal("0"),
            q_versabile_delta=Decimal("0"),
            s_versabile_delta=Decimal("0"),
            drawer_cash_delta=Decimal("0"),
            drawer_checks_delta=Decimal("0"),
            q_cash_delta=Decimal("0"),
            q_checks_delta=Decimal("0"),
            s_cash_delta=Decimal("0"),
            s_checks_delta=Decimal("0"),
        )

    # Movimenti personali/non fiscali (vault): contribuiscono solo alla cassa (per quadratura fisica)
    if flag in {"x", "+"}:
        # nel tuo schema non hanno assegni
        if is_check:
            raise ValueError("check not allowed for flag '+'/'x'")

        if not off_cash:
            cash_delta = signed
            drawer_cash = signed

        return AgendaDeltas(
            cash_delta=cash_delta,
            q_versabile_delta=Decimal("0"),
            s_versabile_delta=Decimal("0"),
            drawer_cash_delta=drawer_cash,
            drawer_checks_delta=Decimal("0"),
            q_cash_delta=Decimal("0"),
            q_checks_delta=Decimal("0"),
            s_cash_delta=Decimal("0"),
            s_checks_delta=Decimal("0"),
        )

    # Fiscali aziendali:
    if flag == "*":
        # cash: sì
        if not off_cash:
            cash_delta = signed
            if is_check:
                drawer_checks = signed
            else:
                drawer_cash = signed

        # Q e S: sì (universale: con segno, quindi out riduce i versabili)
        # Nota assegni:
        # - Q assegni SOLO se maturi e ancora in cassa
        # - S assegni SEMPRE (aziendale), indipendente da maturità
        if is_check:
            if check_mature and check_in_cash:
                qv = signed
                q_checks = signed
            sv = signed
            s_checks = signed
        else:
            qv = signed
            q_cash = signed
            sv = signed
            s_cash = signed

    elif flag == "**":
        # cash: sì
        if not off_cash:
            cash_delta = signed
            if is_check:
                drawer_checks = signed
            else:
                drawer_cash = signed

        # Q: no
        # S: sì (universale con segno)
        if is_check:
            sv = signed
            s_checks = signed
        else:
            sv = signed
            s_cash = signed

    elif flag == "!":
        # cash: no
        # Q e S: sì (universale con segno)
        # (non ammette assegni, per tua specifica)
        if is_check:
            raise ValueError("check not allowed for flag '!'")

        qv = signed
        q_cash = signed
        sv = signed
        s_cash = signed

    else:
        raise ValueError(f"Unhandled flag: {flag!r}")

    return AgendaDeltas(
        cash_delta=cash_delta,
        q_versabile_delta=qv,
        s_versabile_delta=sv,
        drawer_cash_delta=drawer_cash,
        drawer_checks_delta=drawer_checks,
        q_cash_delta=q_cash,
        q_checks_delta=q_checks,
        s_cash_delta=s_cash,
        s_checks_delta=s_checks,
    )


def deltas_to_dict(d: AgendaDeltas) -> Dict[str, str]:
    """
    Helper opzionale: serializza i Decimal come stringhe (per JSON/debug).
    """
    return {
        "cash_delta": str(d.cash_delta),
        "q_versabile_delta": str(d.q_versabile_delta),
        "s_versabile_delta": str(d.s_versabile_delta),
        "drawer_cash_delta": str(d.drawer_cash_delta),
        "drawer_checks_delta": str(d.drawer_checks_delta),
        "q_cash_delta": str(d.q_cash_delta),
        "q_checks_delta": str(d.q_checks_delta),
        "s_cash_delta": str(d.s_cash_delta),
        "s_checks_delta": str(d.s_checks_delta),
    }

"""Centralized product-price visibility and price-list selection."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


PRICE_LIST_LABELS = {
    "prezzo1": "Prezzo 1 (imponibile)",
    "prezzo3": "Prezzo 3 (IVA compresa)",
    "costo": "Costo",
}


def format_euro(value):
    """Formatta un importo nel formato applicativo ``€. 1.000,000``."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None
    sign = "-" if amount < 0 else ""
    integer, decimals = format(abs(amount), ",.3f").split(".")
    return f"{sign}€. {integer.replace(',', '.')},{decimals}"


def iva_compresa_price(article, selected, value=None):
    """Restituisce il prezzo IVA compresa per il listino imponibile."""
    if selected != "prezzo1":
        return None
    prezzo3 = getattr(article, "prezzo_3", None)
    if prezzo3 is not None:
        return prezzo3
    imponibile = value if value is not None else getattr(article, "prezzo_1", None)
    aliquota = getattr(article, "aliquota_iva", None)
    if imponibile is None or aliquota is None:
        return None
    try:
        return Decimal(str(imponibile)) * (Decimal("1") + Decimal(str(aliquota)) / Decimal("100"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def selectable_price_lists(user):
    """Listini selezionabili dal personale; clienti e Horeca restano automatici."""
    if not user or not getattr(user, "is_authenticated", True):
        return []
    if getattr(user, "has_active_role", lambda *_: False)("customer", "customer_horeca"):
        return []
    weight = int(getattr(user, "max_role_weight", 0) or 0)
    if weight < 30:
        return []
    keys = ["prezzo1", "prezzo3"]
    if weight >= 40:
        keys.append("costo")
    return [(key, PRICE_LIST_LABELS[key]) for key in keys]


def normalize_price_list(value, *, allow_cost=False, default="prezzo3"):
    value = str(value or "").strip().lower().replace("_", "")
    allowed = {"prezzo1", "prezzo3"}
    if allow_cost:
        allowed.add("costo")
    return value if value in allowed else default


def visible_product_price(article, user=None, registry=None):
    """Restituisce il prezzo consentito dal ruolo corrente, oppure None."""
    if not user or not getattr(user, "is_authenticated", True):
        return None, None

    if getattr(user, "has_active_role", lambda *_: False)("customer_horeca"):
        registry = registry or getattr(user, "customer_registry", None)
        selected = normalize_price_list(getattr(registry, "listino_prezzo", None), default="prezzo3")
    elif getattr(user, "has_active_role", lambda *_: False)("customer"):
        selected = "prezzo3"
    else:
        weight = int(getattr(user, "max_role_weight", 0) or 0)
        if weight >= 40:
            selected = normalize_price_list(getattr(user, "listino_prezzo", None), allow_cost=True)
        elif weight >= 30:
            selected = normalize_price_list(getattr(user, "listino_prezzo", None), default="prezzo3")
        else:
            return None, None

    value = {
        "prezzo1": getattr(article, "prezzo_1", None),
        "prezzo3": getattr(article, "prezzo_3", None),
        "costo": getattr(article, "costo", None),
    }.get(selected)
    if value is None and selected == "prezzo3":
        value = getattr(article, "prezzo", None)
    if value is None:
        return None, selected
    return value, selected

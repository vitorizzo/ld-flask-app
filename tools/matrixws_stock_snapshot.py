"""Decode MATRIXWS stock snapshots, without adding repeated snapshots."""
from decimal import Decimal, InvalidOperation


def collect_matrixws_stock(rows):
    stock = {}
    seen = set()
    counters = dict(total_rows=len(rows), accepted_rows=0, invalid_rows=0,
                    unsupported_depot_rows=0, duplicate_rows=0)
    for row in rows:
        code = str(row.get('M-CODMAGPR') or '').strip()
        depot = str(row.get('M-DEP') or '').strip()
        if not code:
            counters['invalid_rows'] += 1
            continue
        field = {'0': 'giac_neg', '400': 'giac_www'}.get(depot)
        if field is None:
            counters['unsupported_depot_rows'] += 1
            continue
        try:
            quantity = Decimal(str(row.get('M-GIACATT') or '0').strip().replace(',', '.'))
            if not quantity.is_finite() or quantity != quantity.to_integral_value():
                raise ValueError('Giacenza non intera')
            quantity = int(quantity)
        except (InvalidOperation, ValueError):
            counters['invalid_rows'] += 1
            continue
        key = (code, depot)
        if key in seen:
            counters['duplicate_rows'] += 1
        seen.add(key)
        # Service 1002 repeats article/depot snapshots. The final record matches
        # the current ERP quantity in all three independently checked samples.
        stock.setdefault(code, dict(giac_neg=0, giac_www=0))[field] = quantity
        counters['accepted_rows'] += 1
    return [dict(cod_art=code, **values) for code, values in stock.items()
            if values['giac_neg'] or values['giac_www']], counters

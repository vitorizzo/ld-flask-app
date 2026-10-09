"""Project imported ledger rows into outstanding documents, without changing data."""
from collections import defaultdict
from decimal import Decimal


def open_account_entries(entries):
    """Exclude technical rows and fully offset documents.

    Match within the same snapshot/customer/document date/number/suffix. Do not
    match accounting reason, receipt reference or installment: invoice headers
    and their receipts have different values in those fields. Missing document
    identity stays visible; credits are never allocated to unrelated invoices.
    Partially offset documents retain all their relevant rows and net balance.
    """
    relevant = [entry for entry in entries if entry.is_balance_relevant]
    groups = defaultdict(list)
    for entry in relevant:
        number = (entry.document_number or '').strip()
        if not number or not number.strip('0') or not entry.document_date:
            continue
        payload = entry.source_payload if isinstance(entry.source_payload, dict) else {}
        key = (entry.import_id, entry.source_customer_code, entry.document_date,
               number, str(payload.get('document_number_suffix') or '').strip())
        groups[key].append(entry)
    closed = set()
    for rows in groups.values():
        if len(rows) > 1 and sum((Decimal(row.signed_amount or 0) for row in rows), Decimal('0')) == 0:
            closed.update(row.id for row in rows)
    return [entry for entry in relevant if entry.id not in closed]

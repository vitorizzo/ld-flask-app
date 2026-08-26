import hashlib
import json
from decimal import Decimal


ACTIVE_ITEM_STATUSES = {"link_active", "awaiting_accounting", "under_review", "partially_accounted", "accounted"}


def is_selectable_settlement_item(entry):
    """Riconosce fatture e note di credito utilizzabili per comporre un pagamento."""
    if not entry or not entry.is_balance_relevant or not entry.document_number:
        return False
    if Decimal(entry.amount or 0) <= 0:
        return False
    return (
        (entry.accounting_side == "D" and entry.accounting_reason == "001")
        or (entry.accounting_side == "A" and entry.accounting_reason == "002")
    )


def account_entry_source_key(entry):
    payload = entry.source_payload if isinstance(entry.source_payload, dict) else {}
    identity = {
        "source_customer_code": str(entry.source_customer_code or "").strip(),
        "record_type": str(payload.get("record_type") or "").strip(),
        "accounting_reason": str(entry.accounting_reason or "").strip(),
        "document_number": str(entry.document_number or "").strip(),
        "document_number_suffix": str(payload.get("document_number_suffix") or "").strip(),
        "installment_number": str(payload.get("installment_number") or "").strip(),
        "document_date": entry.document_date.isoformat() if entry.document_date else "",
        "due_date": entry.due_date.isoformat() if entry.due_date else "",
        "accounting_reference": str(entry.accounting_reference or "").strip(),
    }
    canonical = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "teamsystem-ec:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def account_entry_snapshot(entry):
    payload = entry.source_payload if isinstance(entry.source_payload, dict) else {}
    return {
        "source_customer_code": entry.source_customer_code,
        "customer_name": entry.customer_name,
        "document_number": entry.document_number,
        "document_number_suffix": payload.get("document_number_suffix"),
        "installment_number": payload.get("installment_number"),
        "registration_date": entry.registration_date.isoformat() if entry.registration_date else None,
        "document_date": entry.document_date.isoformat() if entry.document_date else None,
        "due_date": entry.due_date.isoformat() if entry.due_date else None,
        "description": entry.description,
        "additional_description": entry.additional_description,
        "accounting_reason": entry.accounting_reason,
        "accounting_reference": entry.accounting_reference,
        "accounting_side": entry.accounting_side,
        "amount": str(entry.amount),
        "signed_amount": str(entry.signed_amount),
    }


def format_iban(value):
    compact = "".join(str(value or "").upper().split())
    if compact.startswith("IT") and len(compact) == 27:
        # Visualizzazione italiana richiesta: paese, CIN, controllo, ABI, CAB, conto.
        groups = (
            compact[:2],
            compact[4:5],
            compact[2:4],
            compact[5:10],
            compact[10:15],
            compact[15:27],
        )
        return " ".join(groups)
    return " ".join(compact[index:index + 4] for index in range(0, len(compact), 4))


def is_valid_iban(value):
    compact = "".join(str(value or "").upper().split())
    if not 15 <= len(compact) <= 34 or not compact.isalnum():
        return False
    rearranged = compact[4:] + compact[:4]
    remainder = 0
    for character in rearranged:
        digits = character if character.isdigit() else str(ord(character) - 55)
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1

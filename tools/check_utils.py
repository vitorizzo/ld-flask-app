from datetime import datetime, timezone
from decimal import Decimal

from extensions import db
from models import CashCheckEvent


def change_check_status(
    check,
    new_status,
    user_id=None,
    event_date=None,
    note=None,
    amount_spese=Decimal("0"),
    customer_charge_amount=Decimal("0"),
):
    """
    Aggiorna lo stato di un assegno e registra lo storico.
    """

    old_status = check.status

    # evita eventi inutili solo se esiste già uno stato precedente
    if old_status is not None and old_status == new_status:
        return

    check.status = new_status

    db.session.add(
        CashCheckEvent(
            check_id=check.id,
            from_status=old_status,
            to_status=new_status,
            event_date=event_date or datetime.now(timezone.utc).date(),
            created_by_user_id=user_id,
            note=note,
            amount_spese=amount_spese,
            customer_charge_amount=customer_charge_amount,
        )
    )
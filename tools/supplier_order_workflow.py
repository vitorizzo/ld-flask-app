"""Persist supplier drafts and atomically replace confirmed order PDFs."""
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from extensions import db
from models import SupplierBoardCard,SupplierBoardColumn,SupplierBoardOrderLine,SupplierOrderProductSettings


class OrderConflict(ValueError):
    pass


def order_rows(group, current_rows, card=None):
    rows={row['root']:dict(row) for row in current_rows}
    if card:
        for line in card.order_lines:
            if line.matrix_code in rows and line.supplier_code is not None:
                rows[line.matrix_code]['supplier_code']=line.supplier_code
                rows[line.matrix_code]['order_description']=line.order_description or line.description
            if line.matrix_code not in rows:
                rows[line.matrix_code]=dict(root=line.matrix_code,description=line.description,stock=line.stock_at_order,
                    subgroup_id=None,subgroup_name=line.subgroup_name or 'Fuori dal gruppo',variants=[],
                    supplier_code=line.supplier_code or '',order_description=line.order_description or line.description,
                    retired=True)
    return rows


def regenerate_order_pdf(card, rows, subgroup_names):
    from tools.supplier_order_pdf import generate_supplier_order_pdf
    if any(not (line.supplier_code or '').strip() for line in card.order_lines):
        raise ValueError('Inserisci il codice fornitore per tutti i prodotti da ordinare.')
    pdf_rows=[dict(row) for row in rows.values()]
    saved={line.matrix_code:line for line in card.order_lines}
    for row in pdf_rows:
        line=saved.get(row['root'])
        if line:
            row['supplier_code']=line.supplier_code
            row['order_description']=line.order_description or line.description
    confirmed=datetime.now(ZoneInfo('Europe/Rome'))
    content=generate_supplier_order_pdf(order_id=card.id,title=card.title,order_date=confirmed.date(),rows=pdf_rows,
        subgroup_names=subgroup_names,quantities={line.matrix_code:line.quantity for line in card.order_lines},single_page=True)
    card.order_pdf=content
    card.order_pdf_filename=f'ordine-fornitore-{card.id}-v{card.order_revision}-{confirmed:%Y%m%d}.pdf'
    card.order_confirmed_at=confirmed.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
    card.is_draft=False


def save_order(group,payload,current_rows):
    """Validate before writing; caller commits, or rolls everything back."""
    draft=payload.get('draft',False)
    if type(draft) is not bool:raise ValueError('Stato bozza non valido.')
    card_id=payload.get('card_id')
    if card_id is not None and (type(card_id) is not int or card_id<=0):raise ValueError('Ordine non valido.')
    key=payload.get('client_key')
    if key is not None and (not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,64}',key)):
        raise ValueError('Chiave bozza non valida.')
    card=SupplierBoardCard.query.filter_by(id=card_id).with_for_update().first() if card_id else None
    if card_id and card is None:raise ValueError('Ordine non trovato.')
    if not card and key:
        existing=SupplierBoardCard.query.filter_by(order_key=key).with_for_update().first()
        if existing:
            if existing.order_group_id!=group.id:raise ValueError('La bozza appartiene a un altro gruppo.')
            return existing,True
    if card:
        if card.is_archived:raise ValueError('Ripristina la scheda prima di modificare l\'ordine.')
        if card.order_group_id not in (None,group.id) or (card.order_group_id is None and not card.order_lines):
            raise ValueError('Ordine non appartenente a questo gruppo.')
        if type(payload.get('revision')) is not int or payload['revision']!=card.order_revision:
            raise OrderConflict('Ordine modificato da un\'altra sessione. Ricarica la versione salvata prima di confermare.')
    rows=order_rows(group,current_rows,card)
    lines=payload.get('lines')
    if not isinstance(lines,list):raise ValueError('Righe ordine non valide.')
    quantities={}
    for line in lines:
        if not isinstance(line,dict):raise ValueError('Riga ordine non valida.')
        code=line.get('matrix_code');quantity=line.get('quantity')
        if not isinstance(code,str) or code not in rows or code in quantities:raise ValueError('Prodotto non valido o duplicato per questo gruppo.')
        if type(quantity) is not int or not 0<=quantity<=1000000:raise ValueError('Le quantita\' devono essere intere, da 0 a 1000000.')
        quantities[code]=quantity
    quantities={code:quantity for code,quantity in quantities.items() if quantity>0}
    if not draft and not quantities:raise ValueError('Inserisci almeno una quantita\' da ordinare.')
    column_id=payload.get('column_id')
    if type(column_id) is not int or db.session.get(SupplierBoardColumn,column_id) is None:raise ValueError('Seleziona una colonna della bacheca.')
    title=payload.get('title','Ordine - '+group.name)
    if not isinstance(title,str) or not title.strip() or len(title.strip())>200:raise ValueError('Inserisci un titolo di massimo 200 caratteri.')
    details=payload.get('product_details',[])
    if not isinstance(details,list):raise ValueError('Codici fornitore non validi.')
    changes={}
    for detail in details:
        if not isinstance(detail,dict) or not isinstance(detail.get('matrix_code'),str) or detail['matrix_code'] not in rows or detail['matrix_code'] in changes:raise ValueError('Prodotto non valido nei codici fornitore.')
        code=detail.get('supplier_code','');description=detail.get('order_description','')
        if not isinstance(code,str) or len(code.strip())>80 or not isinstance(description,str) or len(description.strip())>200:
            raise ValueError('Codice fornitore massimo 80 caratteri; descrizione ordine massimo 200.')
        changes[detail['matrix_code']]=(code.strip(),description.strip())
        rows[detail['matrix_code']]['supplier_code']=code.strip()
        rows[detail['matrix_code']]['order_description']=description.strip()
    if not draft and any(not rows[code].get('supplier_code') for code in quantities):
        raise ValueError('Inserisci il codice fornitore per tutti i prodotti da ordinare.')
    settings={setting.matrix_code:setting for setting in group.product_settings}
    for code,(supplier_code,description) in changes.items():
        setting=settings.get(code)
        if setting is None:setting=SupplierOrderProductSettings(group_id=group.id,matrix_code=code);db.session.add(setting)
        setting.supplier_code=supplier_code;setting.order_description=description
    new=card is None
    if new:card=SupplierBoardCard(order_key=key,notes='Creato dal gruppo: '+group.name)
    card.title=title.strip();card.column_id=column_id;card.order_group_id=group.id
    card.order_revision=1 if new else card.order_revision+1
    card.is_draft=draft
    existing_lines={line.matrix_code:line for line in card.order_lines}
    subgroup_names={row.id:row.name for row in group.subgroups}
    for code,line in existing_lines.items():
        if code not in quantities:card.order_lines.remove(line)
    for code,quantity in quantities.items():
        row=rows[code];line=existing_lines.get(code)
        if line is None:line=SupplierBoardOrderLine(matrix_code=code);card.order_lines.append(line)
        line.quantity=quantity;line.description=row['description'];line.stock_at_order=row['stock']
        line.subgroup_name=row.get('subgroup_name') or subgroup_names.get(row.get('subgroup_id'))
        line.supplier_code=row.get('supplier_code','')
        line.order_description=(row.get('order_description') or row['description'])[:200]
    db.session.add(card);db.session.flush()
    if not draft:regenerate_order_pdf(card,rows,subgroup_names)
    return card,False

from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from datetime import date
from flask_login import current_user
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from extensions import db
from models import Articoli, Giacenza, SupplierOrderGroup, SupplierOrderGroupItem, SupplierOrderMatrixName
from tools.role_required import role_required
from models import SupplierBoardColumn, SupplierBoardCard, BusinessRegistry
from models import SupplierOrderSubgroup, SupplierOrderSubgroupMatrix
from models import SupplierBoardOrderLine


supplier_orders_bp = Blueprint("supplier_orders", __name__, template_folder="../templates")

MIN_SUPPLIER_ORDERS_WEIGHT = 40


def _supplier_card_dict(card, supplier_names=None):
    if supplier_names is None:
        row = db.session.query(BusinessRegistry.display_name).filter_by(id=card.supplier_id).first() if card.supplier_id else None
        supplier_names = {card.supplier_id: row[0]} if row else {}
    return dict(id=card.id, column_id=card.column_id, supplier_id=card.supplier_id,
                supplier_name=supplier_names.get(card.supplier_id),
                title=card.title, notes=card.notes or "", reference=card.reference or "",
                expected_date=card.expected_date.isoformat() if card.expected_date else "",
                is_archived=card.is_archived,
                order_lines=[dict(matrix_code=line.matrix_code, description=line.description,
                                  subgroup_name=line.subgroup_name or "", quantity=line.quantity,
                                  stock_at_order=line.stock_at_order) for line in card.order_lines])


@supplier_orders_bp.get("/board")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def board():
    return render_template("supplier_orders/board.html")


@supplier_orders_bp.get("/api/board")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def board_data():
    columns = SupplierBoardColumn.query.order_by(SupplierBoardColumn.order_index, SupplierBoardColumn.id).all()
    query = SupplierBoardCard.query.options(selectinload(SupplierBoardCard.order_lines))
    if request.args.get("archived") != "1":
        query = query.filter_by(is_archived=False)
    cards = query.order_by(SupplierBoardCard.expected_date.asc().nullslast(), SupplierBoardCard.id.desc()).all()
    supplier_ids = {card.supplier_id for card in cards if card.supplier_id}
    supplier_names = dict(db.session.query(BusinessRegistry.id, BusinessRegistry.display_name).filter(BusinessRegistry.id.in_(supplier_ids)).all()) if supplier_ids else {}
    return jsonify(ok=True, columns=[dict(id=c.id, name=c.name, is_terminal=c.is_terminal) for c in columns],
                   cards=[_supplier_card_dict(card, supplier_names) for card in cards])


@supplier_orders_bp.route("/api/board/cards", methods=["POST"])
@supplier_orders_bp.route("/api/board/cards/<int:card_id>", methods=["PUT"])
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def board_save_card(card_id=None):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error="Dati scheda non validi"), 400
    card = db.session.get(SupplierBoardCard, card_id) if card_id else SupplierBoardCard()
    if card_id and card is None:
        return jsonify(ok=False, error="Scheda non trovata"), 404
    try:
        title = payload.get("title", card.title or "")
        notes = payload.get("notes", card.notes or "")
        reference = payload.get("reference", card.reference or "")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
            raise ValueError("Inserisci un titolo (massimo 200 caratteri).")
        if not isinstance(notes, str) or len(notes) > 40000 or not isinstance(reference, str) or len(reference) > 160:
            raise ValueError("Note o riferimento troppo lunghi.")
        column_id = payload.get("column_id", card.column_id)
        if type(column_id) is not int or db.session.get(SupplierBoardColumn, column_id) is None:
            raise ValueError("Seleziona una colonna valida.")
        supplier_id = payload.get("supplier_id", card.supplier_id)
        if supplier_id is not None and (type(supplier_id) is not int or db.session.query(BusinessRegistry.id).filter_by(id=supplier_id, kind="supplier", is_active=True).first() is None):
            raise ValueError("Seleziona un fornitore attivo della Rubrica.")
        expected = payload.get("expected_date", card.expected_date.isoformat() if card.expected_date else "")
        expected_date = date.fromisoformat(expected) if expected else None
        archived = payload.get("is_archived", card.is_archived or False)
        if type(archived) is not bool:
            raise ValueError("Archiviazione non valida.")
    except (ValueError, TypeError) as exc:
        return jsonify(ok=False, error=str(exc) if isinstance(exc, ValueError) else "Dati scheda non validi"), 400
    card.title = title.strip(); card.notes = notes.strip(); card.reference = reference.strip()
    card.column_id = column_id; card.supplier_id = supplier_id; card.expected_date = expected_date; card.is_archived = archived
    db.session.add(card)
    db.session.commit()
    return jsonify(ok=True, card=_supplier_card_dict(card)), 200 if card_id else 201


def _variant_root(cod_art: str) -> str:
    code = (cod_art or "").strip()
    if "-" not in code:
        return code
    root, suffix = code.rsplit("-", 1)
    if suffix.isdigit() and (
        len(suffix) == 2
        or (len(suffix) == 4 and suffix.startswith(("19", "20")))
    ):
        return root
    return code


def _variant_sort_key(cod_art: str) -> tuple[int, str]:
    code = (cod_art or "").strip()
    suffix = code.rsplit("-", 1)[-1] if "-" in code else ""
    if suffix.isdigit() and len(suffix) == 2:
        value = int(suffix)
        return ((1900 if value >= 70 else 2000) + value, code)
    if suffix.isdigit() and len(suffix) == 4:
        return (int(suffix), code)
    return (0, code)


def _article_label(article: Articoli | None, fallback: str = "") -> str:
    if not article:
        return fallback
    parts = [
        (article.descrizione or "").strip(),
        (article.descrizione_aggiuntiva or "").strip(),
    ]
    label = " - ".join(part for part in parts if part)
    return label or article.cod_art


def _base_description(label: str) -> str:
    text = (label or "").strip()
    return " ".join(part for part in text.split() if not (len(part) == 4 and part.isdigit() and part.startswith(("19", "20"))))


def _stock_map(codes: list[str]) -> dict[str, int]:
    if not codes:
        return {}
    rows = (
        db.session.query(Giacenza.cod_art, func.coalesce(Giacenza.giac_neg, 0) + func.coalesce(Giacenza.giac_www, 0))
        .filter(Giacenza.cod_art.in_(codes))
        .all()
    )
    return {str(code): int(qty or 0) for code, qty in rows if code}


def _expanded_articles_for_group(group: SupplierOrderGroup) -> list[dict]:
    selected_codes = [item.cod_art for item in group.items]
    roots = sorted({_variant_root(code) for code in selected_codes if code})
    if not roots:
        return []

    filters = []
    for root in roots:
        filters.append(Articoli.cod_art == root)
        filters.append(Articoli.cod_art.like(f"{root}-%"))

    articles = (
        Articoli.query
        .filter(or_(*filters))
        .order_by(Articoli.descrizione.asc(), Articoli.cod_art.asc())
        .all()
    )
    stock = _stock_map([article.cod_art for article in articles])
    selected_roots = {_variant_root(code) for code in selected_codes}

    custom_names = {item.matrix_code: item.display_name for item in group.matrix_names}
    subgroup_map = {item.matrix_code: item.subgroup_id for item in getattr(group, "subgroup_matrices", [])}
    grouped: dict[str, dict] = {}
    for article in articles:
        root = _variant_root(article.cod_art)
        label = _article_label(article)
        if root not in grouped:
            grouped[root] = {
                "root": root,
                "subgroup_id": subgroup_map.get(root),
                "description": "",
                "default_description": "",
                "custom_description": custom_names.get(root),
                "stock": 0,
                "selected_count": 0,
                "variants": [],
            }
        variant = {
            "cod_art": article.cod_art,
            "root": root,
            "description": label,
            "stock": stock.get(article.cod_art, 0),
            "source_selected": article.cod_art in selected_codes,
            "expanded_from_group": root in selected_roots and article.cod_art not in selected_codes,
        }
        grouped[root]["stock"] += variant["stock"]
        grouped[root]["selected_count"] += 1 if variant["source_selected"] else 0
        grouped[root]["variants"].append(variant)

    for row in grouped.values():
        latest_variant = max(row["variants"], key=lambda variant: _variant_sort_key(variant["cod_art"]))
        row["default_description"] = latest_variant["description"]
        row["description"] = row["custom_description"] or row["default_description"]

    return sorted(grouped.values(), key=lambda row: (row["description"] or "", row["root"]))


@supplier_orders_bp.get("/")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def index():
    active_group_id = request.args.get("group_id", type=int)
    modal_action = (request.args.get("modal") or "").strip()
    groups = (
        SupplierOrderGroup.query
        .order_by(SupplierOrderGroup.is_active.desc(), SupplierOrderGroup.name.asc())
        .all()
    )
    group_cards = [
        {
            "group": group,
            "operational_rows": _expanded_articles_for_group(group),
        }
        for group in groups
    ]
    for card in group_cards:
        rows = card["operational_rows"]
        sections = [dict(name=subgroup.name, rows=[row for row in rows if row["subgroup_id"] == subgroup.id]) for subgroup in card["group"].subgroups]
        unassigned = [row for row in rows if row["subgroup_id"] is None]
        if unassigned:
            sections.append(dict(name="Senza sottogruppo" if card["group"].subgroups else "", rows=unassigned))
        card["stock_sections"] = [dict(section, stock=sum(row["stock"] for row in section["rows"])) for section in sections if section["rows"]]
    return render_template(
        "supplier_orders/index.html",
        group_cards=group_cards,
        active_group_id=active_group_id,
        modal_action=modal_action,
        order_columns=SupplierBoardColumn.query.order_by(SupplierBoardColumn.is_terminal, SupplierBoardColumn.order_index, SupplierBoardColumn.id).all(),
    )


@supplier_orders_bp.post("/groups/<int:group_id>/orders")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def create_group_order(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error="Dati ordine non validi."), 400
    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        return jsonify(ok=False, error="Inserisci almeno una quantita' da ordinare."), 400
    rows = {row["root"]: row for row in _expanded_articles_for_group(group)}
    seen = set()
    for line in lines:
        if not isinstance(line, dict):
            return jsonify(ok=False, error="Riga ordine non valida."), 400
        code = line.get("matrix_code")
        quantity = line.get("quantity")
        if not isinstance(code, str) or code not in rows or code in seen:
            return jsonify(ok=False, error="Prodotto non valido o duplicato per questo gruppo."), 400
        if type(quantity) is not int or not 1 <= quantity <= 1000000:
            return jsonify(ok=False, error="Le quantita' devono essere intere, da 1 a 1000000."), 400
        seen.add(code)
    column_id = payload.get("column_id")
    if type(column_id) is not int or db.session.get(SupplierBoardColumn, column_id) is None:
        return jsonify(ok=False, error="Seleziona una colonna della bacheca."), 400
    title = payload.get("title", "Ordine - " + group.name)
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        return jsonify(ok=False, error="Inserisci un titolo di massimo 200 caratteri."), 400
    subgroup_names = {row.id: row.name for row in group.subgroups}
    card = SupplierBoardCard(title=title.strip(), column_id=column_id, notes="Creato dal gruppo: " + group.name)
    for line in lines:
        row = rows[line["matrix_code"]]
        card.order_lines.append(SupplierBoardOrderLine(matrix_code=row["root"], description=row["description"],
            subgroup_name=subgroup_names.get(row["subgroup_id"]), quantity=line["quantity"], stock_at_order=row["stock"]))
    db.session.add(card); db.session.commit()
    return jsonify(ok=True, card=_supplier_card_dict(card)), 201


@supplier_orders_bp.post("/groups")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def create_group():
    name = (request.form.get("name") or "").strip()
    notes = (request.form.get("notes") or "").strip() or None
    if not name:
        return redirect(url_for("supplier_orders.index"))

    existing = SupplierOrderGroup.query.filter(func.lower(SupplierOrderGroup.name) == name.lower()).first()
    if existing:
        existing.is_active = True
        existing.notes = notes if notes is not None else existing.notes
        db.session.commit()
        return redirect(url_for("supplier_orders.index", group_id=existing.id, modal="manage"))

    group = SupplierOrderGroup(
        name=name,
        notes=notes,
        created_by_user_id=current_user.id if current_user.is_authenticated else None,
    )
    db.session.add(group)
    db.session.commit()
    return redirect(url_for("supplier_orders.index", group_id=group.id, modal="manage"))


@supplier_orders_bp.post("/groups/<int:group_id>/update")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def update_group(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    group.name = (request.form.get("name") or group.name).strip()
    group.notes = (request.form.get("notes") or "").strip() or None
    group.is_active = request.form.get("is_active") == "1"
    db.session.commit()
    return redirect(url_for("supplier_orders.index", group_id=group.id))


@supplier_orders_bp.post("/groups/<int:group_id>/delete")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def delete_group(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    return redirect(url_for("supplier_orders.index"))


@supplier_orders_bp.get("/groups/<int:group_id>/items")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def group_items(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    subgroup_map = {row.matrix_code: row.subgroup_id for row in group.subgroup_matrices}
    items = sorted(
        (
            {
                "cod_art": item.cod_art,
                "description": _article_label(item.article, item.cod_art),
                "root": _variant_root(item.cod_art),
                "subgroup_id": subgroup_map.get(_variant_root(item.cod_art)),
            }
            for item in group.items
        ),
        key=lambda item: ((item["description"] or "").lower(), item["cod_art"].lower()),
    )
    return jsonify({"ok": True, "group": {"id": group.id, "name": group.name}, "items": items,
                    "subgroups": [dict(id=row.id, name=row.name) for row in group.subgroups]})


@supplier_orders_bp.route("/groups/<int:group_id>/subgroups", methods=["POST"])
@supplier_orders_bp.route("/groups/<int:group_id>/subgroups/<int:subgroup_id>", methods=["PUT", "DELETE"])
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def save_subgroup(group_id, subgroup_id=None):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    subgroup = SupplierOrderSubgroup.query.filter_by(group_id=group.id, id=subgroup_id).first_or_404() if subgroup_id else None
    if request.method == "DELETE":
        db.session.delete(subgroup)
        db.session.commit()
        return jsonify(ok=True)
    payload = request.get_json(silent=True)
    name = payload.get("name") if isinstance(payload, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 160:
        return jsonify(ok=False, error="Inserisci un nome di massimo 160 caratteri."), 400
    name = name.strip()
    existing = SupplierOrderSubgroup.query.filter_by(group_id=group.id).filter(func.lower(SupplierOrderSubgroup.name) == name.lower()).first()
    if existing and (not subgroup or existing.id != subgroup.id):
        return jsonify(ok=False, error="Questo sottogruppo esiste gia'."), 400
    if subgroup is None:
        subgroup = SupplierOrderSubgroup(group_id=group.id)
    subgroup.name = name
    db.session.add(subgroup); db.session.commit()
    return jsonify(ok=True, subgroup=dict(id=subgroup.id, name=subgroup.name))


@supplier_orders_bp.post("/groups/<int:group_id>/subgroup-assignment")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def assign_subgroup(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error="Dati non validi."), 400
    codes = payload.get("codes")
    if not isinstance(codes, list) or not codes or any(not isinstance(code, str) for code in codes):
        return jsonify(ok=False, error="Seleziona i prodotti del gruppo."), 400
    selected = {item.cod_art for item in group.items}
    if not set(codes).issubset(selected):
        return jsonify(ok=False, error="Alcuni prodotti non appartengono al gruppo."), 400
    subgroup_id = payload.get("subgroup_id")
    if subgroup_id is not None and (type(subgroup_id) is not int or SupplierOrderSubgroup.query.filter_by(id=subgroup_id, group_id=group.id).first() is None):
        return jsonify(ok=False, error="Sottogruppo non valido per questo gruppo."), 400
    roots = {_variant_root(code) for code in codes}
    assignments = {row.matrix_code: row for row in group.subgroup_matrices}
    for root in roots:
        row = assignments.get(root)
        if subgroup_id is None:
            if row: db.session.delete(row)
        elif row:
            row.subgroup_id = subgroup_id
        else:
            db.session.add(SupplierOrderSubgroupMatrix(group_id=group.id, subgroup_id=subgroup_id, matrix_code=root))
    db.session.commit()
    return jsonify(ok=True, assigned=len(roots))


@supplier_orders_bp.post("/groups/<int:group_id>/items/batch")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def update_group_items(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    payload = request.get_json(silent=True) or {}
    add_codes = {str(code).strip() for code in (payload.get("add_codes") or []) if str(code).strip()}
    remove_codes = {str(code).strip() for code in (payload.get("remove_codes") or []) if str(code).strip()}

    valid_add_codes = {
        code for (code,) in db.session.query(Articoli.cod_art).filter(Articoli.cod_art.in_(add_codes)).all()
    } if add_codes else set()
    existing = {item.cod_art: item for item in group.items}
    for code in remove_codes:
        item = existing.get(code)
        if item:
            db.session.delete(item)
    next_sort = max((item.sort_order or 0 for item in group.items), default=0)
    for code in sorted(valid_add_codes - set(existing)):
        next_sort += 10
        db.session.add(SupplierOrderGroupItem(group_id=group.id, cod_art=code, sort_order=next_sort))
    db.session.commit()
    return jsonify({"ok": True, "added": len(valid_add_codes - set(existing)), "removed": len(remove_codes & set(existing))})


@supplier_orders_bp.post("/groups/<int:group_id>/matrix-name")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def update_matrix_name(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    payload = request.get_json(silent=True) or {}
    matrix_code = (payload.get("matrix_code") or "").strip()
    display_name = (payload.get("display_name") or "").strip()
    valid_matrices = {_variant_root(item.cod_art) for item in group.items}
    if not matrix_code or matrix_code not in valid_matrices:
        return jsonify({"ok": False, "error": "Codice matrice non valido per il gruppo"}), 400

    custom_name = SupplierOrderMatrixName.query.filter_by(group_id=group.id, matrix_code=matrix_code).first()
    if display_name:
        if custom_name:
            custom_name.display_name = display_name
        else:
            db.session.add(SupplierOrderMatrixName(group_id=group.id, matrix_code=matrix_code, display_name=display_name))
    elif custom_name:
        db.session.delete(custom_name)
    db.session.commit()
    return jsonify({"ok": True, "matrix_code": matrix_code, "display_name": display_name})


@supplier_orders_bp.post("/groups/<int:group_id>/items")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def add_item(group_id):
    group = SupplierOrderGroup.query.get_or_404(group_id)
    cod_art = (request.form.get("cod_art") or "").strip()
    if not cod_art:
        return redirect(url_for("supplier_orders.index", group_id=group.id))
    article = Articoli.query.filter_by(cod_art=cod_art).first()
    if not article:
        return redirect(url_for("supplier_orders.index", group_id=group.id))

    existing = SupplierOrderGroupItem.query.filter_by(group_id=group.id, cod_art=cod_art).first()
    if not existing:
        next_sort = (db.session.query(func.coalesce(func.max(SupplierOrderGroupItem.sort_order), 0)).filter_by(group_id=group.id).scalar() or 0) + 10
        db.session.add(SupplierOrderGroupItem(group_id=group.id, cod_art=cod_art, sort_order=next_sort))
        db.session.commit()
    return redirect(url_for("supplier_orders.index", group_id=group.id))


@supplier_orders_bp.post("/groups/<int:group_id>/items/<int:item_id>/delete")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def delete_item(group_id, item_id):
    item = SupplierOrderGroupItem.query.filter_by(group_id=group_id, id=item_id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("supplier_orders.index", group_id=group_id))


@supplier_orders_bp.get("/api/articles")
@role_required(MIN_SUPPLIER_ORDERS_WEIGHT)
def search_articles():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"ok": True, "items": []})

    rows = (
        Articoli.query
        .filter(or_(
            Articoli.cod_art.ilike(f"%{q}%"),
            Articoli.descrizione.ilike(f"%{q}%"),
            Articoli.descrizione_aggiuntiva.ilike(f"%{q}%"),
        ))
        .order_by(Articoli.descrizione.asc(), Articoli.cod_art.asc())
        .limit(100)
        .all()
    )
    return jsonify({
        "ok": True,
        "items": [
            {"cod_art": row.cod_art, "description": _article_label(row), "root": _variant_root(row.cod_art)}
            for row in rows
        ],
    })

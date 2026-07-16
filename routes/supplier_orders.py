from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from extensions import db
from models import Articoli, InventarioExport, SupplierOrderGroup, SupplierOrderGroupItem, SupplierOrderMatrixName
from tools.role_required import role_required


supplier_orders_bp = Blueprint("supplier_orders", __name__, template_folder="../templates")

MIN_SUPPLIER_ORDERS_WEIGHT = 40


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
        db.session.query(InventarioExport.articolo_id, func.coalesce(func.sum(InventarioExport.giacenza), 0))
        .filter(InventarioExport.articolo_id.in_(codes))
        .group_by(InventarioExport.articolo_id)
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
    grouped: dict[str, dict] = {}
    for article in articles:
        root = _variant_root(article.cod_art)
        label = _article_label(article)
        if root not in grouped:
            grouped[root] = {
                "root": root,
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
    return render_template(
        "supplier_orders/index.html",
        group_cards=group_cards,
        active_group_id=active_group_id,
        modal_action=modal_action,
    )


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
    items = sorted(
        (
            {
                "cod_art": item.cod_art,
                "description": _article_label(item.article, item.cod_art),
                "root": _variant_root(item.cod_art),
            }
            for item in group.items
        ),
        key=lambda item: ((item["description"] or "").lower(), item["cod_art"].lower()),
    )
    return jsonify({"ok": True, "group": {"id": group.id, "name": group.name}, "items": items})


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

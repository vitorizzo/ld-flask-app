from decimal import Decimal, InvalidOperation
import secrets

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from models import Articoli, BusinessRegistry, WineCard, WineCardItem, WineCardSection, WineCardTemplate
from tools.role_required import role_required


wine_cards_bp = Blueprint("wine_cards", __name__, template_folder="../templates")


def _customer_label(customer):
    if not customer:
        return ""
    return customer.display_name or customer.legal_name or customer.source_code or f"Cliente {customer.id}"


def _new_customer_view_token():
    while True:
        token = secrets.token_urlsafe(32)
        if not WineCard.query.filter_by(customer_view_token=token).first():
            return token


def _parse_money(value):
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _form_bool(name):
    return "1" in request.form.getlist(name)


def _article_display_description(article):
    parts = [article.descrizione or "", article.descrizione_aggiuntiva or ""]
    return " ".join(part.strip() for part in parts if part and part.strip()).strip()


def _section_code(title):
    value = (title or "").strip().lower()
    replacements = {
        "à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    cleaned = []
    for char in value:
        cleaned.append(char if char.isalnum() else "_")
    code = "_".join(part for part in "".join(cleaned).split("_") if part)
    return code or "sezione"


def _ensure_section(card, title):
    title = (title or "").strip() or "Selezione"
    base_code = _section_code(title)
    existing = next((section for section in card.sections if section.code == base_code), None)
    if existing:
        return existing
    code = base_code
    suffix = 2
    while WineCardSection.query.filter_by(card_id=card.id, code=code).first():
        code = f"{base_code}_{suffix}"
        suffix += 1
    section = WineCardSection(
        card_id=card.id,
        code=code,
        title=title,
        sort_order=max([row.sort_order for row in card.sections] or [-1]) + 1,
        is_visible=True,
    )
    db.session.add(section)
    db.session.flush()
    card.sections.append(section)
    return section


def _sections_with_items(card, *, visible_only=False):
    sections = sorted(card.sections or [], key=lambda row: (row.sort_order, row.id or 0))
    section_ids = {section.id for section in sections}
    orphan_items = []
    rows = []
    for section in sections:
        if visible_only and not section.is_visible:
            continue
        items = [
            item for item in sorted(section.items or [], key=lambda row: (row.sort_order, row.id or 0))
            if not visible_only or item.is_visible
        ]
        if items or not visible_only:
            rows.append((section, items))
    for item in sorted(card.items or [], key=lambda row: (row.sort_order, row.id or 0)):
        if item.section_id not in section_ids and (not visible_only or item.is_visible):
            orphan_items.append(item)
    if orphan_items:
        rows.append((None, orphan_items))
    return rows


def _staff_customer_options(limit=120):
    return (
        BusinessRegistry.query
        .filter(BusinessRegistry.kind == "customer", BusinessRegistry.is_active.is_(True))
        .order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
        .limit(limit)
        .all()
    )


def _active_templates():
    return (
        WineCardTemplate.query
        .filter(WineCardTemplate.is_active.is_(True))
        .order_by(WineCardTemplate.sort_order.asc(), WineCardTemplate.name.asc())
        .all()
    )


def _default_template_id():
    template = (
        WineCardTemplate.query
        .filter(WineCardTemplate.is_active.is_(True))
        .order_by(WineCardTemplate.sort_order.asc(), WineCardTemplate.id.asc())
        .first()
    )
    return template.id if template else None


def _merged_layout_config(card):
    config = dict(card.template.layout_config or {}) if card.template else {}
    config.update(card.layout_config or {})
    return config


def _view_style_vars(config):
    mapping = {
        "font_family": "--wine-font",
        "heading_font_family": "--wine-heading-font",
        "accent_font_family": "--wine-accent-font",
        "text_color": "--wine-text-color",
        "background_color": "--wine-bg",
        "heading_size": "--wine-heading-size",
        "subtitle_size": "--wine-subtitle-size",
        "section_size": "--wine-section-size",
        "item_size": "--wine-item-size",
        "meta_size": "--wine-meta-size",
        "price_x": "--wine-price-x",
        "item_gap": "--wine-item-gap",
        "section_gap": "--wine-section-gap",
    }
    parts = []
    for key, css_var in mapping.items():
        value = (config.get(key) or "").strip() if isinstance(config.get(key), str) else config.get(key)
        if value:
            parts.append(f"{css_var}: {value}")
    return "; ".join(parts)


@wine_cards_bp.get("/")
@login_required
@role_required(30)
def index():
    q = (request.args.get("q") or "").strip()
    query = WineCard.query.outerjoin(BusinessRegistry, WineCard.customer_registry_id == BusinessRegistry.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            WineCard.title.ilike(like),
            WineCard.venue_name.ilike(like),
            BusinessRegistry.display_name.ilike(like),
            BusinessRegistry.legal_name.ilike(like),
            BusinessRegistry.source_code.ilike(like),
        ))
    cards = query.order_by(WineCard.updated_at.desc(), WineCard.id.desc()).limit(200).all()
    return render_template("wine_cards/index.html", cards=cards, q=q, customer_label=_customer_label)


@wine_cards_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required(30)
def create():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            title = "Nuova carta vini"
        card = WineCard(
            title=title,
            template_id=request.form.get("template_id", type=int) or _default_template_id(),
            venue_name=(request.form.get("venue_name") or "").strip() or None,
            subtitle=(request.form.get("subtitle") or "").strip() or None,
            customer_registry_id=request.form.get("customer_registry_id", type=int),
            status="draft",
            customer_view_enabled=request.form.get("customer_view_enabled") == "1",
            customer_view_token=_new_customer_view_token(),
            layout_config={
                "font_family": (request.form.get("font_family") or "").strip() or "serif",
                "background": (request.form.get("background") or "").strip() or None,
                "logo_position": (request.form.get("logo_position") or "").strip() or "top",
            },
            created_by_user_id=current_user.id,
        )
        db.session.add(card)
        db.session.commit()
        return redirect(url_for("wine_cards.detail", card_id=card.id))
    return render_template("wine_cards/form.html", card=None, customers=_staff_customer_options(), templates=_active_templates())


@wine_cards_bp.get("/<int:card_id>")
@login_required
@role_required(30)
def detail(card_id):
    card = WineCard.query.get_or_404(card_id)
    return render_template(
        "wine_cards/detail.html",
        card=card,
        customer_label=_customer_label,
        sections_with_items=_sections_with_items(card),
        templates=_active_templates(),
    )


@wine_cards_bp.post("/<int:card_id>/update")
@login_required
@role_required(30)
def update(card_id):
    card = WineCard.query.get_or_404(card_id)
    card.title = (request.form.get("title") or "").strip() or card.title
    card.venue_name = (request.form.get("venue_name") or "").strip() or None
    card.subtitle = (request.form.get("subtitle") or "").strip() or None
    card.customer_registry_id = request.form.get("customer_registry_id", type=int)
    card.template_id = request.form.get("template_id", type=int) or None
    card.status = (request.form.get("status") or "draft").strip() or "draft"
    card.customer_view_enabled = request.form.get("customer_view_enabled") == "1"
    card.layout_config = {
        "font_family": (request.form.get("font_family") or "").strip() or "serif",
        "background": (request.form.get("background") or "").strip() or None,
        "logo_position": (request.form.get("logo_position") or "").strip() or "top",
    }
    if not card.customer_view_token:
        card.customer_view_token = _new_customer_view_token()
    db.session.commit()
    return redirect(url_for("wine_cards.detail", card_id=card.id))


@wine_cards_bp.post("/<int:card_id>/duplicate")
@login_required
@role_required(30)
def duplicate(card_id):
    source = WineCard.query.get_or_404(card_id)
    card = WineCard(
        customer_registry_id=source.customer_registry_id,
        template_id=source.template_id,
        source_card_id=source.id,
        created_by_user_id=current_user.id,
        title=f"Copia di {source.title}",
        venue_name=source.venue_name,
        subtitle=source.subtitle,
        status="draft",
        customer_view_enabled=False,
        customer_view_token=_new_customer_view_token(),
        layout_config=dict(source.layout_config or {}),
    )
    db.session.add(card)
    db.session.flush()
    section_map = {}
    for section in source.sections or []:
        copy_section = WineCardSection(
            card_id=card.id,
            code=section.code,
            title=section.title,
            sort_order=section.sort_order,
            is_visible=section.is_visible,
            notes=section.notes,
        )
        db.session.add(copy_section)
        db.session.flush()
        section_map[section.id] = copy_section.id
    for index, item in enumerate(source.items or []):
        db.session.add(WineCardItem(
            card_id=card.id,
            section_id=section_map.get(item.section_id),
            cod_art=item.cod_art,
            sort_order=index,
            category=item.category,
            display_description=item.display_description,
            winery=item.winery,
            region=item.region,
            sale_price=item.sale_price,
            is_visible=item.is_visible,
            notes=item.notes,
        ))
    db.session.commit()
    return redirect(url_for("wine_cards.detail", card_id=card.id))


@wine_cards_bp.post("/<int:card_id>/items")
@login_required
@role_required(30)
def add_item(card_id):
    card = WineCard.query.get_or_404(card_id)
    cod_art = (request.form.get("cod_art") or "").strip()
    article = Articoli.query.filter_by(cod_art=cod_art).first() if cod_art else None
    if not article:
        abort(404)
    section_title = (request.form.get("section_title") or request.form.get("category") or "").strip()
    section = _ensure_section(card, section_title)
    next_order = (max([item.sort_order for item in card.items] or [-1]) + 1)
    item = WineCardItem(
        card_id=card.id,
        section_id=section.id,
        cod_art=article.cod_art,
        sort_order=next_order,
        category=section.title,
        display_description=(request.form.get("display_description") or "").strip() or _article_display_description(article),
        winery=(request.form.get("winery") or "").strip() or None,
        region=(request.form.get("region") or "").strip() or None,
        sale_price=_parse_money(request.form.get("sale_price")) or article.prezzo,
        is_visible=True,
    )
    db.session.add(item)
    db.session.commit()
    return redirect(url_for("wine_cards.detail", card_id=card.id))


@wine_cards_bp.post("/<int:card_id>/items/<int:item_id>/update")
@login_required
@role_required(30)
def update_item(card_id, item_id):
    item = WineCardItem.query.filter_by(card_id=card_id, id=item_id).first_or_404()
    card = item.card
    section_title = (request.form.get("section_title") or request.form.get("category") or "").strip()
    section = _ensure_section(card, section_title) if section_title else None
    item.section_id = section.id if section else None
    item.sort_order = request.form.get("sort_order", type=int) or 0
    item.category = section.title if section else None
    item.display_description = (request.form.get("display_description") or "").strip() or item.display_description
    item.winery = (request.form.get("winery") or "").strip() or None
    item.region = (request.form.get("region") or "").strip() or None
    item.sale_price = _parse_money(request.form.get("sale_price"))
    item.is_visible = _form_bool("is_visible")
    item.notes = (request.form.get("notes") or "").strip() or None
    db.session.commit()
    return redirect(url_for("wine_cards.detail", card_id=card_id))


@wine_cards_bp.post("/<int:card_id>/sections")
@login_required
@role_required(30)
def add_section(card_id):
    card = WineCard.query.get_or_404(card_id)
    _ensure_section(card, request.form.get("title"))
    db.session.commit()
    return redirect(url_for("wine_cards.detail", card_id=card.id))


@wine_cards_bp.post("/<int:card_id>/sections/<int:section_id>/update")
@login_required
@role_required(30)
def update_section(card_id, section_id):
    section = WineCardSection.query.filter_by(card_id=card_id, id=section_id).first_or_404()
    title = (request.form.get("title") or "").strip()
    if title:
        section.title = title
        new_code = _section_code(title)
        conflict = WineCardSection.query.filter(
            WineCardSection.card_id == card_id,
            WineCardSection.code == new_code,
            WineCardSection.id != section.id,
        ).first()
        if not conflict:
            section.code = new_code
    section.sort_order = request.form.get("sort_order", type=int) or 0
    section.is_visible = _form_bool("is_visible")
    section.notes = (request.form.get("notes") or "").strip() or None
    for item in section.items or []:
        item.category = section.title
    db.session.commit()
    return redirect(url_for("wine_cards.detail", card_id=card_id))


@wine_cards_bp.post("/<int:card_id>/items/<int:item_id>/delete")
@login_required
@role_required(30)
def delete_item(card_id, item_id):
    item = WineCardItem.query.filter_by(card_id=card_id, id=item_id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("wine_cards.detail", card_id=card_id))


@wine_cards_bp.get("/api/articles")
@login_required
@role_required(30)
def api_articles():
    q = (request.args.get("q") or "").strip()
    query = Articoli.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Articoli.cod_art.ilike(like),
            Articoli.descrizione.ilike(like),
            Articoli.descrizione_aggiuntiva.ilike(like),
        ))
    rows = query.order_by(Articoli.descrizione.asc(), Articoli.cod_art.asc()).limit(30).all()
    return jsonify({"ok": True, "articles": [
        {
            "cod_art": row.cod_art,
            "description": _article_display_description(row),
            "price": float(row.prezzo) if row.prezzo is not None else None,
        }
        for row in rows
    ]})


@wine_cards_bp.get("/view/<token>")
@login_required
@role_required(30, roles=["customer_horeca"])
def customer_view(token):
    card = WineCard.query.filter_by(customer_view_token=token).first_or_404()
    if (current_user.max_role_weight or 0) < 30 and not card.customer_view_enabled:
        abort(403)
    visible_items = [item for item in card.items if item.is_visible]
    return render_template(
        "wine_cards/view.html",
        card=card,
        visible_items=visible_items,
        sections_with_items=_sections_with_items(card, visible_only=True),
        layout_config=_merged_layout_config(card),
        style_vars=_view_style_vars(_merged_layout_config(card)),
        back_url=request.args.get("back") or url_for("wine_cards.detail", card_id=card.id),
        customer_label=_customer_label,
        customer_mode=(current_user.max_role_weight or 0) < 30,
    )

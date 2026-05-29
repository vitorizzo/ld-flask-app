from decimal import Decimal, InvalidOperation
import secrets
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from extensions import db
from models import Articoli, BusinessRegistry, WineCard, WineCardItem, WineCardSection, WineCardTemplate
from tools.role_required import role_required


wine_cards_bp = Blueprint("wine_cards", __name__, template_folder="../templates")

ASSET_UPLOADS = {
    "customer_logo": ("loghi_clienti", {"png", "jpg", "jpeg", "webp"}),
    "company_logo": ("loghi_azienda", {"png", "jpg", "jpeg", "webp"}),
    "background_image": ("backgrounds", {"png", "jpg", "jpeg", "webp"}),
}
LOGO_VERTICAL_POSITIONS = {"header", "footer"}
LOGO_ALIGNMENTS = {"left", "center", "right"}
TEXT_LAYOUT_ELEMENTS = {
    "venue": {
        "label": "Insegna",
        "size": 14,
        "font": "var(--wine-heading-font)",
        "color": "",
        "align": "center",
        "bold": False,
        "italic": False,
        "uppercase": False,
    },
    "title": {
        "label": "Titolo carta",
        "size": 20,
        "font": "var(--wine-heading-font)",
        "color": "",
        "align": "center",
        "bold": True,
        "italic": False,
        "uppercase": False,
    },
    "subtitle": {
        "label": "Sottotitolo",
        "size": 14,
        "font": "var(--wine-accent-font)",
        "color": "",
        "align": "center",
        "bold": False,
        "italic": False,
        "uppercase": False,
    },
    "section": {
        "label": "Titoli sezione",
        "size": 15,
        "font": "var(--wine-heading-font)",
        "color": "#735338",
        "align": "left",
        "bold": True,
        "italic": False,
        "uppercase": True,
    },
    "item": {
        "label": "Nome articolo",
        "size": 14,
        "font": "var(--wine-font)",
        "color": "",
        "align": "left",
        "bold": False,
        "italic": False,
        "uppercase": False,
    },
    "meta": {
        "label": "Cantina e regione",
        "size": 11,
        "font": "var(--wine-font)",
        "color": "#71665d",
        "align": "left",
        "bold": False,
        "italic": False,
        "uppercase": False,
    },
    "price": {
        "label": "Prezzo",
        "size": 14,
        "font": "var(--wine-font)",
        "color": "",
        "align": "right",
        "bold": True,
        "italic": False,
        "uppercase": False,
    },
}
FONT_OPTIONS = [
    ("var(--wine-font)", "Base"),
    ("var(--wine-heading-font)", "Titoli"),
    ("var(--wine-accent-font)", "Corsivo decorativo"),
    ("serif", "Serif"),
    ("sans-serif", "Sans serif"),
    ("monospace", "Monospace"),
]
ALIGN_OPTIONS = [("left", "Sinistra"), ("center", "Centro"), ("right", "Destra")]


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


def _asset_options(field_name):
    folder_name, allowed_ext = ASSET_UPLOADS[field_name]
    asset_dir = Path(wine_cards_bp.root_path).parent / "static" / "images" / folder_name
    if not asset_dir.exists():
        return []
    options = []
    for path in sorted(asset_dir.iterdir(), key=lambda row: row.name.lower()):
        if path.is_file() and path.suffix.lower().lstrip(".") in allowed_ext:
            options.append({
                "label": path.name,
                "value": f"images/{folder_name}/{path.name}",
            })
    return options


def _asset_options_by_field():
    return {field_name: _asset_options(field_name) for field_name in ASSET_UPLOADS}


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
        "background_image_opacity": "--wine-bg-opacity",
    }
    parts = []
    for key, css_var in mapping.items():
        value = (config.get(key) or "").strip() if isinstance(config.get(key), str) else config.get(key)
        if value:
            parts.append(f"{css_var}: {value}")
    return "; ".join(parts)


def _coerce_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _coerce_float(value, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _layout_visible(config, key, default=True):
    value = config.get(f"{key}_visible")
    return default if value is None else bool(value)


def _text_element_style(config, key):
    defaults = TEXT_LAYOUT_ELEMENTS[key]
    styles = {
        "font-size": f"{_coerce_int(config.get(f'{key}_size_pt'), defaults['size'], 6, 60)}pt",
        "font-family": config.get(f"{key}_font_family") or defaults["font"],
        "text-align": config.get(f"{key}_align") or defaults["align"],
        "font-weight": "700" if _layout_visible(config, f"{key}_bold", defaults["bold"]) else "400",
        "font-style": "italic" if _layout_visible(config, f"{key}_italic", defaults["italic"]) else "normal",
        "text-transform": "uppercase" if _layout_visible(config, f"{key}_uppercase", defaults["uppercase"]) else "none",
    }
    color = config.get(f"{key}_color") or defaults["color"]
    if color:
        styles["color"] = color
    return "; ".join(f"{name}: {value}" for name, value in styles.items())


def _text_element_styles(config):
    return {key: _text_element_style(config, key) for key in TEXT_LAYOUT_ELEMENTS}


def _visible_elements(config):
    visible = {key: _layout_visible(config, key, True) for key in TEXT_LAYOUT_ELEMENTS}
    visible.update({
        "company_logo": _layout_visible(config, "company_logo", True),
        "customer_logo": _layout_visible(config, "customer_logo", True),
        "background_image": _layout_visible(config, "background_image", True),
    })
    return visible


def _logo_height(value, default=18):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(8, min(parsed, 60))


def _layout_logo_config(config, logo_key, default_vertical="header", default_align="left"):
    vertical = (request.form.get(f"{logo_key}_vertical") or config.get(f"{logo_key}_vertical") or default_vertical).strip()
    align = (request.form.get(f"{logo_key}_align") or config.get(f"{logo_key}_align") or default_align).strip()
    config[f"{logo_key}_vertical"] = vertical if vertical in LOGO_VERTICAL_POSITIONS else default_vertical
    config[f"{logo_key}_align"] = align if align in LOGO_ALIGNMENTS else default_align
    config[f"{logo_key}_height_mm"] = _logo_height(
        request.form.get(f"{logo_key}_height_mm") or config.get(f"{logo_key}_height_mm"),
        default=18,
    )


def _logo_layout(config):
    slots = {
        "header": {"left": [], "center": [], "right": []},
        "footer": {"left": [], "center": [], "right": []},
    }
    for logo_key, alt, default_align in [
        ("company_logo", "Logo azienda", "left"),
        ("customer_logo", "Logo cliente", "right"),
    ]:
        if not _layout_visible(config, logo_key, True):
            continue
        path = config.get(logo_key)
        if not path:
            continue
        vertical = config.get(f"{logo_key}_vertical") or "header"
        align = config.get(f"{logo_key}_align") or default_align
        if vertical not in slots:
            vertical = "header"
        if align not in slots[vertical]:
            align = default_align
        slots[vertical][align].append({
            "path": path,
            "alt": alt,
            "height": _logo_height(config.get(f"{logo_key}_height_mm"), default=18),
        })
    return slots


def _save_card_asset(field_name):
    uploaded = request.files.get(field_name)
    if not uploaded or not uploaded.filename:
        return None
    folder_name, allowed_ext = ASSET_UPLOADS[field_name]
    original = secure_filename(uploaded.filename)
    suffix = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if suffix not in allowed_ext:
        abort(400)
    stem = original.rsplit(".", 1)[0] if "." in original else original
    filename = f"{stem}-{secrets.token_hex(4)}.{suffix}"
    target_dir = Path(wine_cards_bp.root_path).parent / "static" / "images" / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    uploaded.save(target_dir / filename)
    return f"images/{folder_name}/{filename}"


def _layout_from_form(existing=None):
    config = dict(existing or {})
    config.update({
        "font_family": (request.form.get("font_family") or "").strip() or "serif",
        "background": (request.form.get("background") or "").strip() or None,
    })
    if "background_image_visible" in request.form:
        config["background_image_visible"] = _form_bool("background_image_visible")
    else:
        config["background_image_visible"] = _layout_visible(config, "background_image", True)
    config["background_image_opacity"] = _coerce_float(
        request.form.get("background_image_opacity") or config.get("background_image_opacity"),
        0.16,
        0,
        1,
    )
    for key, defaults in TEXT_LAYOUT_ELEMENTS.items():
        if f"{key}_visible" in request.form:
            config[f"{key}_visible"] = _form_bool(f"{key}_visible")
        else:
            config[f"{key}_visible"] = _layout_visible(config, key, True)
        config[f"{key}_size_pt"] = _coerce_int(request.form.get(f"{key}_size_pt"), defaults["size"], 6, 60)
        font_family = (request.form.get(f"{key}_font_family") or defaults["font"]).strip()
        config[f"{key}_font_family"] = font_family
        color = (request.form.get(f"{key}_color") or "").strip()
        config[f"{key}_color"] = color or defaults["color"] or None
        align = (request.form.get(f"{key}_align") or defaults["align"]).strip()
        config[f"{key}_align"] = align if align in {value for value, _ in ALIGN_OPTIONS} else defaults["align"]
        config[f"{key}_bold"] = _form_bool(f"{key}_bold") if f"{key}_bold" in request.form else _layout_visible(config, f"{key}_bold", defaults["bold"])
        config[f"{key}_italic"] = _form_bool(f"{key}_italic") if f"{key}_italic" in request.form else _layout_visible(config, f"{key}_italic", defaults["italic"])
        config[f"{key}_uppercase"] = _form_bool(f"{key}_uppercase") if f"{key}_uppercase" in request.form else _layout_visible(config, f"{key}_uppercase", defaults["uppercase"])

    config["company_logo_visible"] = _form_bool("company_logo_visible") if "company_logo_visible" in request.form else _layout_visible(config, "company_logo", True)
    config["customer_logo_visible"] = _form_bool("customer_logo_visible") if "customer_logo_visible" in request.form else _layout_visible(config, "customer_logo", True)
    for field_name in ASSET_UPLOADS:
        selected_path = (request.form.get(f"{field_name}_selected") or "").strip()
        if selected_path == "__clear__":
            config.pop(field_name, None)
        elif selected_path:
            folder_name = ASSET_UPLOADS[field_name][0]
            if selected_path.startswith(f"images/{folder_name}/"):
                config[field_name] = selected_path

    _layout_logo_config(config, "company_logo", default_vertical="header", default_align="left")
    _layout_logo_config(config, "customer_logo", default_vertical="header", default_align="right")

    for field_name in ASSET_UPLOADS:
        saved_path = _save_card_asset(field_name)
        if saved_path:
            config[field_name] = saved_path
    return config


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
            layout_config=_layout_from_form(),
            created_by_user_id=current_user.id,
        )
        db.session.add(card)
        db.session.commit()
        return redirect(url_for("wine_cards.detail", card_id=card.id))
    return render_template(
        "wine_cards/form.html",
        card=None,
        customers=_staff_customer_options(),
        templates=_active_templates(),
        asset_options=_asset_options_by_field(),
        text_layout_elements=TEXT_LAYOUT_ELEMENTS,
        font_options=FONT_OPTIONS,
        align_options=ALIGN_OPTIONS,
    )


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
        asset_options=_asset_options_by_field(),
        text_layout_elements=TEXT_LAYOUT_ELEMENTS,
        font_options=FONT_OPTIONS,
        align_options=ALIGN_OPTIONS,
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
    card.layout_config = _layout_from_form(card.layout_config or {})
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
    layout_config = _merged_layout_config(card)
    return render_template(
        "wine_cards/view.html",
        card=card,
        visible_items=visible_items,
        sections_with_items=_sections_with_items(card, visible_only=True),
        layout_config=layout_config,
        logo_layout=_logo_layout(layout_config),
        element_styles=_text_element_styles(layout_config),
        visible_elements=_visible_elements(layout_config),
        style_vars=_view_style_vars(layout_config),
        back_url=request.args.get("back") or url_for("wine_cards.detail", card_id=card.id),
        customer_label=_customer_label,
        customer_mode=(current_user.max_role_weight or 0) < 30,
    )

"""Theme tokens shared by the application shell and reusable components."""

from __future__ import annotations

import copy
import re

from models import AppPreference
from extensions import db


THEME_KEY = "ui.theme"

DEFAULT_THEME = {
    "preset": "default",
    "brand_primary": "#4a2c2a",
    "brand_accent": "#0dcaf0",
    "surface": "#ffffff",
    "surface_muted": "#4a2c2a",
    "text": "#ffffff",
    "text_muted": "#f1d9d0",
    "radius": 10,
    "page_padding": 18,
    "base_font_size": 16,
    "touch_size": 48,
    "modal_width": 720,
    "modal_radius": 10,
    "navbar_divider": 1,
    "footer_divider": 1,
    "navbar_divider_style": "brush",
    "footer_divider_style": "brush",
    "divider_color": "#b18b77",
    "divider_width": 1,
}

THEME_PRESETS = {
    "default": {"label": "LDApp (attuale)", "values": {}},
    "high_contrast": {
        "label": "Alto contrasto",
        "values": {
            "brand_primary": "#102a43", "brand_accent": "#b45309",
            "surface": "#ffffff", "surface_muted": "#eef2f7",
            "text": "#0f172a", "text_muted": "#334155",
        },
    },
    "soft": {
        "label": "Soft",
        "values": {
            "brand_primary": "#315a68", "brand_accent": "#8bc3b7",
            "surface": "#ffffff", "surface_muted": "#f0faf7",
            "text": "#172033", "text_muted": "#64748b",
        },
    },
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_NUMBER_RANGES = {
    "radius": (0, 32), "page_padding": (0, 48), "base_font_size": (14, 22),
    "touch_size": (44, 72), "modal_width": (320, 1400), "modal_radius": (0, 32), "divider_width": (1, 6),
}


def _clean_theme(value):
    result = copy.deepcopy(DEFAULT_THEME)
    if isinstance(value, dict):
        result.update({key: value[key] for key in result if key in value})
    for key in ("brand_primary", "brand_accent", "surface", "surface_muted", "text", "text_muted", "divider_color"):
        if not _HEX.match(str(result[key])):
            result[key] = DEFAULT_THEME[key]
    for key, (low, high) in _NUMBER_RANGES.items():
        try:
            result[key] = max(low, min(high, int(result[key])))
        except (TypeError, ValueError):
            result[key] = DEFAULT_THEME[key]
    for key in ("navbar_divider", "footer_divider"):
        result[key] = 1 if str(result.get(key)).lower() in {"1", "true", "yes", "on"} else 0
    for key in ("navbar_divider_style", "footer_divider_style"):
        if result.get(key) not in {"brush", "line", "none"}:
            result[key] = "brush" if result.get(key.replace("_style", "")) else "none"
    if result.get("preset") not in THEME_PRESETS:
        result["preset"] = "default"
    return result


def load_theme():
    row = AppPreference.query.filter_by(key=THEME_KEY).first()
    return _clean_theme(row.value_json if row else None)


def save_theme(value):
    theme = _clean_theme(value)
    row = AppPreference.query.filter_by(key=THEME_KEY).first()
    if row is None:
        row = AppPreference(key=THEME_KEY, category="Aspetto grafico", label="Tema applicativo", value_type="json", sort_order=10)
        db.session.add(row)
    row.category = "Aspetto grafico"
    row.label = "Tema applicativo"
    row.description = "Token grafici condivisi da pagine, modali e componenti responsive."
    row.value_type = "json"
    row.value_json = theme
    row.value_text = None
    row.secret_value = None
    db.session.commit()
    return theme


def theme_css_vars(theme=None):
    theme = _clean_theme(theme or load_theme())
    return "; ".join([
        f"--ld-brand-primary: {theme['brand_primary']}",
        f"--ld-brand-accent: {theme['brand_accent']}",
        f"--ld-surface: {theme['surface']}",
        f"--ld-surface-muted: {theme['surface_muted']}",
        f"--ld-text: {theme['text']}",
        f"--ld-text-muted: {theme['text_muted']}",
        f"--ld-radius: {theme['radius']}px",
        f"--ld-page-padding: {theme['page_padding']}px",
        f"--ld-base-font-size: {theme['base_font_size']}px",
        f"--ld-touch-size: {theme['touch_size']}px",
        f"--ld-modal-width: {theme['modal_width']}px",
        f"--ld-modal-radius: {theme['modal_radius']}px",
        f"--ld-divider-color: {theme['divider_color']}",
        f"--ld-divider-width: {theme['divider_width']}px",
    ])

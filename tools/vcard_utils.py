from __future__ import annotations

import base64
import binascii
import quopri
import re
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_VCARD_BYTES = 2 * 1024 * 1024
MAX_PHOTO_BYTES = 5 * 1024 * 1024


@dataclass
class ParsedVCard:
    display_name: str = ""
    phones: list[dict] = field(default_factory=list)
    emails: list[dict] = field(default_factory=list)
    photo_bytes: bytes | None = None
    photo_mime: str | None = None


def _unfold_lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    folded: list[str] = []
    for line in text.split("\n"):
        if line.startswith((" ", "\t")) and folded:
            folded[-1] += line[1:]
        else:
            folded.append(line)
    unfolded: list[str] = []
    for line in folded:
        if unfolded and "QUOTED-PRINTABLE" in unfolded[-1].split(":", 1)[0].upper() and unfolded[-1].endswith("="):
            unfolded[-1] = unfolded[-1][:-1] + line
        else:
            unfolded.append(line)
    return unfolded


def _decode_text(value: str, parameters: str) -> str:
    raw = value.encode("utf-8", errors="replace")
    if "QUOTED-PRINTABLE" in parameters.upper():
        raw = quopri.decodestring(raw)
        charset_match = re.search(r"CHARSET=([^;:]+)", parameters, re.I)
        charset = charset_match.group(1) if charset_match else "utf-8"
        try:
            value = raw.decode(charset, errors="replace")
        except LookupError:
            value = raw.decode("utf-8", errors="replace")
    return (
        value.replace("\\n", " ").replace("\\N", " ")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
        .strip()
    )


def _type_label(parameters: str) -> tuple[str, bool]:
    upper = parameters.upper()
    is_mobile = any(token in upper for token in ("CELL", "MOBILE", "IPHONE"))
    if is_mobile:
        return "Cellulare", True
    if "WORK" in upper:
        return "Lavoro", False
    if "HOME" in upper:
        return "Casa", False
    return "", False


def _decode_photo(value: str, parameters: str) -> tuple[bytes | None, str | None]:
    upper = parameters.upper()
    mime = "image/png" if "PNG" in upper else "image/jpeg"
    payload = value.strip()
    if payload.lower().startswith("data:image/"):
        header, separator, payload = payload.partition(",")
        if not separator or ";base64" not in header.lower():
            return None, None
        mime = header[5:].split(";", 1)[0].lower()
    elif "ENCODING=B" not in upper and "ENCODING=BASE64" not in upper:
        return None, None
    try:
        decoded = base64.b64decode(re.sub(r"\s+", "", payload), validate=False)
    except (binascii.Error, ValueError):
        return None, None
    if not decoded or len(decoded) > MAX_PHOTO_BYTES:
        return None, None
    return decoded, mime


def normalize_contact_photo(photo_bytes: bytes) -> bytes:
    if not photo_bytes or len(photo_bytes) > MAX_PHOTO_BYTES:
        raise ValueError("Foto contatto assente o troppo grande")
    try:
        with Image.open(BytesIO(photo_bytes)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A")
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Formato della foto contatto non valido") from exc


def parse_vcard(raw: bytes) -> ParsedVCard:
    if not raw:
        raise ValueError("Il file vCard e' vuoto")
    if len(raw) > MAX_VCARD_BYTES:
        raise ValueError("Il file vCard supera il limite di 2 MB")
    text = raw.decode("utf-8-sig", errors="replace")
    card_match = re.search(r"BEGIN:VCARD[\s\S]*?END:VCARD", text, re.I)
    lines = _unfold_lines(card_match.group(0) if card_match else text)
    fields: list[tuple[str, str, str]] = []
    photo_bytes = None
    photo_mime = None

    for line in lines:
        metadata, separator, value = line.partition(":")
        if not separator:
            continue
        parts = metadata.split(";")
        property_name = parts.pop(0).split(".")[-1].upper()
        parameters = ";".join(parts)
        if property_name == "PHOTO" and photo_bytes is None:
            photo_bytes, photo_mime = _decode_photo(value, parameters)
            continue
        fields.append((property_name, parameters, _decode_text(value, parameters)))

    def first(name: str) -> str:
        return next((value for prop, _, value in fields if prop == name and value), "")

    display_name = first("FN")
    if not display_name:
        structured = first("N").split(";")
        structured += [""] * (5 - len(structured))
        display_name = " ".join(
            item for item in (structured[3], structured[1], structured[2], structured[0], structured[4]) if item
        ).strip()

    phones = []
    emails = []
    for prop, parameters, value in fields:
        if prop not in {"TEL", "EMAIL"} or not value:
            continue
        value = re.sub(r"^(?:tel:|mailto:)", "", value, flags=re.I).strip()
        label, is_mobile = _type_label(parameters)
        target = phones if prop == "TEL" else emails
        item = {"value": value, "label": label, "is_primary": "PREF" in parameters.upper()}
        if prop == "TEL":
            item["contact_type"] = "mobile" if is_mobile else "phone"
        else:
            item["contact_type"] = "email"
        if not any(existing["value"].casefold() == value.casefold() for existing in target):
            target.append(item)

    if phones and not any(item["is_primary"] for item in phones):
        preferred = next((item for item in phones if item["contact_type"] == "mobile"), phones[0])
        preferred["is_primary"] = True
    if emails and not any(item["is_primary"] for item in emails):
        emails[0]["is_primary"] = True

    if not display_name and not phones and not emails:
        raise ValueError("La vCard non contiene nome, telefono o email leggibili")
    if photo_bytes:
        photo_bytes = normalize_contact_photo(photo_bytes)
        photo_mime = "image/jpeg"
    return ParsedVCard(display_name, phones, emails, photo_bytes, photo_mime)

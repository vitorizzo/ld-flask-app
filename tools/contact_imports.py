from __future__ import annotations

import os
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta

from flask import current_app

from extensions import db
from models import RegistryContact, RegistryContactImportIntent, RegistryContactPoint
from tools.vcard_utils import parse_vcard


VCARD_MIME_TYPES = {
    "text/vcard",
    "text/x-vcard",
    "text/directory",
    "application/vcard",
    "application/x-vcard",
}


def is_vcard_upload(upload) -> bool:
    filename = (getattr(upload, "filename", "") or "").lower()
    mime = (getattr(upload, "mimetype", "") or "").split(";", 1)[0].lower()
    return filename.endswith(".vcf") or mime in VCARD_MIME_TYPES


def _photo_root() -> str:
    root = os.path.abspath(os.path.join(current_app.instance_path, "registry_contact_photos"))
    os.makedirs(root, exist_ok=True)
    return root


def resolve_photo_path(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    root = _photo_root()
    candidate = os.path.abspath(os.path.join(root, relative_path.replace("/", os.sep)))
    if not candidate.startswith(root + os.sep) or not os.path.isfile(candidate):
        return None
    return candidate


def create_contact_import_intent(
    upload,
    user_id: int | None,
    suggested_registry_id: int | None = None,
    *,
    claim_token_hash: str | None = None,
    claim_expires_at: datetime | None = None,
):
    parsed = parse_vcard(upload.read())
    photo_path = None
    if parsed.photo_bytes:
        relative = os.path.join("pending", f"{uuid.uuid4().hex}.jpg")
        absolute = os.path.join(_photo_root(), relative)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, "wb") as handle:
            handle.write(parsed.photo_bytes)
        photo_path = relative.replace(os.sep, "/")
    intent = RegistryContactImportIntent(
        user_id=user_id,
        suggested_registry_id=suggested_registry_id,
        source_filename=(upload.filename or "contatto.vcf")[:255],
        display_name=parsed.display_name[:255] or None,
        phones=parsed.phones,
        emails=parsed.emails,
        photo_path=photo_path,
        photo_mime=parsed.photo_mime,
        claim_token_hash=claim_token_hash,
        claim_expires_at=claim_expires_at,
    )
    db.session.add(intent)
    db.session.commit()
    return intent


def create_claimable_contact_import_intent(upload):
    token = secrets.token_urlsafe(32)
    intent = create_contact_import_intent(
        upload,
        None,
        claim_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        claim_expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    return intent, token


def claim_contact_import_intent(intent, user_id: int, token: str) -> bool:
    if intent.user_id is not None or not token or not intent.claim_token_hash:
        return False
    if not intent.claim_expires_at or intent.claim_expires_at < datetime.utcnow():
        return False
    candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(candidate, intent.claim_token_hash):
        return False
    intent.user_id = user_id
    intent.claim_token_hash = None
    intent.claim_expires_at = None
    db.session.commit()
    return True


def _move_intent_photo(intent, contact) -> None:
    source = resolve_photo_path(intent.photo_path)
    if not source:
        return
    relative = os.path.join("contacts", f"contact-{contact.id}-{uuid.uuid4().hex[:10]}.jpg")
    target = os.path.join(_photo_root(), relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(source, target)
    contact.photo_path = relative.replace(os.sep, "/")
    contact.photo_mime = "image/jpeg"
    intent.photo_path = None


def finalize_contact_import(intent, registry, display_name: str, selected_keys: list[str] | None, role: str = "", notes: str = ""):
    available = {}
    for category, values in (("phone", intent.phones or []), ("email", intent.emails or [])):
        for index, point in enumerate(values):
            available[f"{category}:{index}"] = point
    selected = list(available.values()) if selected_keys is None else [available[key] for key in selected_keys if key in available]

    contact = None
    for point in selected:
        contact = (
            RegistryContact.query
            .join(RegistryContactPoint, RegistryContactPoint.contact_id == RegistryContact.id)
            .filter(
                RegistryContact.is_active.is_(True),
                RegistryContactPoint.contact_type == point["contact_type"],
                RegistryContactPoint.value == point["value"],
            )
            .order_by(RegistryContact.id.asc())
            .first()
        )
        if contact:
            break

    reused = contact is not None
    if not contact:
        contact = RegistryContact(display_name=display_name, role=role or None, notes=notes or None)
        db.session.add(contact)
        for point in selected:
            contact.points.append(RegistryContactPoint(
                contact_type=point["contact_type"],
                value=point["value"],
                label=point.get("label") or None,
                is_primary=bool(point.get("is_primary")),
            ))
        db.session.flush()
    if intent.photo_path:
        if not contact.photo_path:
            _move_intent_photo(intent, contact)
        else:
            pending_photo = resolve_photo_path(intent.photo_path)
            if pending_photo:
                os.remove(pending_photo)
            intent.photo_path = None
    intent.status = "completed"
    return contact, reused

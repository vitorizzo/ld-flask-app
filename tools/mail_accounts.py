import smtplib

from flask import current_app
from sqlalchemy import inspect

from extensions import db


SYSTEM_EMAIL_ACCOUNTS = {
    "general": {"name": "Email generale", "prefix": "MAIL", "fallback_prefix": None},
    "assistance": {"name": "Email assistenza", "prefix": "ASSISTANCE_MAIL", "fallback_prefix": "MAIL"},
}


def config_bool(key, default=False):
    value = current_app.config.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _config_value(prefix, key, fallback_prefix=None, default=None):
    value = current_app.config.get(f"{prefix}_{key}")
    if value not in (None, ""):
        return value
    if fallback_prefix:
        value = current_app.config.get(f"{fallback_prefix}_{key}")
        if value not in (None, ""):
            return value
    return default


def _legacy_account(code):
    definition = SYSTEM_EMAIL_ACCOUNTS.get(code)
    if not definition:
        return None
    prefix = definition["prefix"]
    fallback = definition["fallback_prefix"]
    return {
        "id": None,
        "code": code,
        "name": definition["name"],
        "smtp_server": _config_value(prefix, "SERVER", fallback),
        "smtp_port": int(_config_value(prefix, "PORT", fallback, 25) or 25),
        "use_tls": config_bool(f"{prefix}_USE_TLS", config_bool(f"{fallback}_USE_TLS", False) if fallback else False),
        "use_ssl": config_bool(f"{prefix}_USE_SSL", config_bool(f"{fallback}_USE_SSL", False) if fallback else False),
        "username": _config_value(prefix, "USERNAME", fallback),
        "password": _config_value(prefix, "PASSWORD", fallback),
        "default_sender": _config_value(prefix, "DEFAULT_SENDER", fallback),
        "imap_server": None,
        "imap_port": 993,
        "imap_use_tls": False,
        "imap_use_ssl": True,
        "imap_username": None,
        "imap_password": None,
        "imap_folder": "INBOX",
        "imap_enabled": False,
        "has_imap_password": False,
        "is_enabled": True,
        "is_system": True,
        "source": ".env.local/runtime",
    }


def get_email_account(code, include_password=True, legacy_fallback=True):
    normalized = str(code or "").strip().lower()
    if not normalized:
        return None

    if inspect(db.engine).has_table("email_accounts"):
        from models import EmailAccount

        account = EmailAccount.query.filter_by(code=normalized).first()
        if account:
            data = account.to_dict()
            data["password"] = account.password_encrypted if include_password else None
            data["imap_password"] = account.imap_password_encrypted if include_password else None
            data["source"] = "database"
            return data

    return _legacy_account(normalized) if legacy_fallback else None


def account_sender(code):
    account = get_email_account(code)
    if account:
        return account.get("default_sender") or account.get("username")
    return None


def assistance_mail_sender():
    return account_sender("assistance") or "assistenza.ldapp@ldenoteca.it"


def send_account_mail(code, message):
    if current_app.testing or config_bool("MAIL_SUPPRESS_SEND", False):
        return

    account = get_email_account(code)
    if not account:
        raise RuntimeError(f"Account email '{code}' non configurato")
    if not account.get("is_enabled"):
        raise RuntimeError(f"Account email '{code}' disattivato")

    server = account.get("smtp_server")
    port = int(account.get("smtp_port") or 25)
    username = account.get("username")
    password = account.get("password")
    if not server:
        raise RuntimeError(f"Server SMTP non configurato per l'account '{code}'")
    if not username or not password:
        raise RuntimeError(f"Credenziali SMTP non configurate per l'account '{code}'")

    message.sender = account.get("default_sender") or username
    recipients = list(message.send_to)
    smtp_cls = smtplib.SMTP_SSL if account.get("use_ssl") else smtplib.SMTP
    with smtp_cls(server, port) as smtp:
        if account.get("use_tls") and not account.get("use_ssl"):
            smtp.starttls()
        smtp.login(username, password)
        smtp.sendmail(message.sender, recipients, message.as_string())


def send_assistance_mail(message):
    return send_account_mail("assistance", message)

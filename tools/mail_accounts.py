import smtplib

from flask import current_app


def config_bool(key, default=False):
    value = current_app.config.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _account_value(prefix, key, fallback_prefix=None, default=None):
    value = current_app.config.get(f"{prefix}_{key}")
    if value not in (None, ""):
        return value
    if fallback_prefix:
        value = current_app.config.get(f"{fallback_prefix}_{key}")
        if value not in (None, ""):
            return value
    return default


def assistance_mail_sender():
    return (
        current_app.config.get("ASSISTANCE_MAIL_DEFAULT_SENDER")
        or current_app.config.get("ASSISTANCE_MAIL_USERNAME")
        or "assistenza.ldapp@ldenoteca.it"
    )


def send_assistance_mail(message):
    if current_app.testing or config_bool("MAIL_SUPPRESS_SEND", False):
        return

    server = _account_value("ASSISTANCE_MAIL", "SERVER", "MAIL")
    port = int(_account_value("ASSISTANCE_MAIL", "PORT", "MAIL", 25) or 25)
    use_tls = config_bool("ASSISTANCE_MAIL_USE_TLS", config_bool("MAIL_USE_TLS", False))
    use_ssl = config_bool("ASSISTANCE_MAIL_USE_SSL", config_bool("MAIL_USE_SSL", False))
    username = _account_value("ASSISTANCE_MAIL", "USERNAME")
    password = _account_value("ASSISTANCE_MAIL", "PASSWORD")

    if not server:
        raise RuntimeError("ASSISTANCE_MAIL_SERVER non configurato")
    if not username or not password:
        raise RuntimeError("Credenziali ASSISTANCE_MAIL_USERNAME/PASSWORD non configurate")

    message.sender = assistance_mail_sender()
    recipients = list(message.send_to)

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(server, port) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        smtp.login(username, password)
        smtp.sendmail(message.sender, recipients, message.as_string())

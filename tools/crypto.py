import os
from sqlalchemy.types import TypeDecorator, String
from cryptography.fernet import Fernet
from flask import current_app


def _get_fernet():
    # recupera la chiave dal Flask app context
    key = current_app.config['FERNET_KEY']
    return Fernet(key.encode())


class EncryptedString(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        f = _get_fernet()
        return f.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        f = _get_fernet()
        return f.decrypt(value.encode()).decode()

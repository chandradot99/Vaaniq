from cryptography.fernet import Fernet

from naaviq.server.core.config import settings


def _get_fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY environment variable is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_key(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()

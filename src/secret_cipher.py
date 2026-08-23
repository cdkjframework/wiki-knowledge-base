from cryptography.fernet import Fernet, InvalidToken


def generate_key() -> str:
    """Return a URL-safe base64 Fernet key."""
    return Fernet.generate_key().decode("utf-8")


def encrypt_text(text: str, key: str) -> str:
    """Encrypt plain text with a Fernet key."""
    if not isinstance(text, str):
        text = str(text)
    if not isinstance(key, str):
        raise TypeError("key must be a string")

    fernet = Fernet(key.encode("utf-8"))
    token = fernet.encrypt(text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(cipher_text: str, key: str) -> str:
    """Decrypt Fernet cipher text back to plain text."""
    if not isinstance(cipher_text, str):
        cipher_text = str(cipher_text)
    if not isinstance(key, str):
        raise TypeError("key must be a string")

    fernet = Fernet(key.encode("utf-8"))
    try:
        plain = fernet.decrypt(cipher_text.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Invalid key or cipher text") from exc
    return plain.decode("utf-8")


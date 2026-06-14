import base64
import hashlib
import os
from cryptography.fernet import Fernet
from app.core.config import settings

def get_fernet_key() -> bytes:
    # 1. Try environment variable
    vault_key = os.getenv("VAULT_ENCRYPTION_KEY")
    if vault_key:
        try:
            # Validate if it's already a valid base64 key for Fernet
            base64.urlsafe_b64decode(vault_key.encode())
            return vault_key.encode()
        except Exception:
            # If invalid format, we derive a key from it
            pass
            
    # 2. Derive key from SECRET_KEY (or invalid environment key)
    source_key = vault_key if vault_key else settings.SECRET_KEY
    derived = hashlib.sha256(source_key.encode()).digest()
    return base64.urlsafe_b64encode(derived)

def encrypt_key(plain_key: str) -> str:
    if not plain_key:
        return ""
    fernet_key = get_fernet_key()
    cipher_suite = Fernet(fernet_key)
    return cipher_suite.encrypt(plain_key.encode()).decode()

def decrypt_key(encrypted_key: str) -> str:
    if not encrypted_key:
        return ""
    fernet_key = get_fernet_key()
    cipher_suite = Fernet(fernet_key)
    return cipher_suite.decrypt(encrypted_key.encode()).decode()

import json
import base64
from cryptography.fernet import Fernet
from django.conf import settings

class EncryptionUtils:
    """
    Helper class for field-level encryption (GDPR Compliance)
    Uses Fernet (symmetric encryption) from cryptography library.
    """
    
    _cipher = None

    @classmethod
    def get_cipher(cls):
        """Get or create Fernet cipher instance"""
        if cls._cipher is None:
            key = settings.ENCRYPTION_KEY
            # Ensure key is bytes - but don't double-encode if already bytes
            if isinstance(key, str):
                key = key.encode()
            # key is now bytes, ready for Fernet
            
            # If key is not valid Fernet key (32 bytes url-safe base64), 
            # we might need to pad or hash it, but Fernet expects specific format.
            # Only if we used a sloppy manual key would we need to fix it.
            # For now, assume proper configuration or our dev fallback.
            try:
                cls._cipher = Fernet(key)
            except ValueError as e:
                import sys
                print(f"FATAL: Invalid ENCRYPTION_KEY format: {e}", file=sys.stderr)
                print(f"Key type: {type(key)}, Length: {len(key) if key else 0}", file=sys.stderr)
                raise ValueError(f"Invalid encryption key: {e}")
                
        return cls._cipher

    @classmethod
    def encrypt(cls, data):
        """
        Encrypt data (dict or str) -> encrypted base64 string
        """
        if data is None:
            return None
            
        if isinstance(data, (dict, list)):
            text = json.dumps(data)
        else:
            text = str(data)
            
        cipher = cls.get_cipher()
        encrypted_bytes = cipher.encrypt(text.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()

    @classmethod
    def decrypt(cls, encrypted_str):
        """
        Decrypt encrypted string -> original data (dict if valid json, else str)
        """
        if not encrypted_str:
            return None
            
        try:
            cipher = cls.get_cipher()
            # Handle potential url-safe decoding if we stored it that way
            # We return urlsafe b64 string from encrypt, so:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_str)
            
            decrypted_bytes = cipher.decrypt(encrypted_bytes)
            decrypted_text = decrypted_bytes.decode()
            
            # Try parsing as JSON
            try:
                return json.loads(decrypted_text)
            except json.JSONDecodeError:
                return decrypted_text
                
        except Exception as e:
            # Depending on security posture, might want to raise or return None
            # Return None means "corrupt or unreadable"
            print(f"Decryption error: {e}") 
            return None

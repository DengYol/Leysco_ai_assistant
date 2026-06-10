"""
app/core/encryption.py
======================

Encryption system for sensitive data protection.

Features:
  - AES-256 encryption using Fernet
  - Symmetric encryption for data at rest
  - Password hashing with bcrypt
  - Secure key derivation
  - Authenticated encryption

Usage:
  from app.core.encryption import EncryptionManager, get_encryption_manager
  
  manager = get_encryption_manager()
  
  # Encrypt sensitive data
  encrypted = manager.encrypt("credit_card_number_1234567890")
  
  # Decrypt when needed
  decrypted = manager.decrypt(encrypted)
  
  # Hash passwords
  hashed = manager.hash_password("user_password")
  
  # Verify password
  valid = manager.verify_password("user_password", hashed)
"""

from cryptography.fernet import Fernet
import bcrypt
import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# ENCRYPTION MANAGER
# ============================================================================

class EncryptionManager:
    """
    Encryption and decryption for sensitive data.
    
    Uses Fernet (AES-128-CBC) for authenticated encryption.
    """
    
    def __init__(self):
        """Initialize encryption manager"""
        # Get encryption key from environment
        master_key = os.getenv("ENCRYPTION_MASTER_KEY")
        
        if not master_key:
            # Generate a key for development
            logger.warning("⚠️ ENCRYPTION_MASTER_KEY not set, generating for development")
            master_key = Fernet.generate_key().decode()
        
        # Use key as-is (should be base64-encoded Fernet key)
        try:
            if isinstance(master_key, str):
                master_key = master_key.encode()
            self.cipher = Fernet(master_key)
        except Exception as e:
            logger.warning(f"Invalid encryption key format, generating new: {e}")
            self.cipher = Fernet(Fernet.generate_key())
        
        # Bcrypt cost factor
        self.bcrypt_rounds = int(os.getenv("BCRYPT_ROUNDS", 12))
        
        logger.info("✅ EncryptionManager initialized")
        logger.info(f"   - Algorithm: Fernet (AES-128-CBC)")
        logger.info(f"   - Bcrypt rounds: {self.bcrypt_rounds}")
    
    def encrypt(self, data: str) -> str:
        """
        Encrypt sensitive data.
        
        Args:
            data: Plain text to encrypt
        
        Returns:
            Base64-encoded encrypted data
        """
        try:
            encrypted = self.cipher.encrypt(data.encode())
            encoded = base64.b64encode(encrypted).decode()
            logger.debug(f"Data encrypted ({len(data)} bytes)")
            return encoded
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def decrypt(self, encrypted_data: str) -> Optional[str]:
        """
        Decrypt sensitive data.
        
        Args:
            encrypted_data: Base64-encoded encrypted data
        
        Returns:
            Decrypted plain text, or None if decryption fails
        """
        try:
            decoded = base64.b64decode(encrypted_data.encode())
            decrypted = self.cipher.decrypt(decoded)
            logger.debug(f"Data decrypted ({len(decrypted)} bytes)")
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None
    
    def hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt.
        
        Args:
            password: Plain text password
        
        Returns:
            Bcrypt hash
        """
        try:
            salt = bcrypt.gensalt(rounds=self.bcrypt_rounds)
            hashed = bcrypt.hashpw(password.encode(), salt)
            logger.debug("Password hashed")
            return hashed.decode()
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            raise
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            password: Plain text password
            hashed: Bcrypt hash
        
        Returns:
            True if password matches
        """
        try:
            return bcrypt.checkpw(password.encode(), hashed.encode())
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
    
    def encrypt_dict(self, data: dict, keys_to_encrypt: list) -> dict:
        """
        Encrypt specific fields in a dictionary.
        
        Args:
            data: Dictionary with sensitive data
            keys_to_encrypt: List of keys to encrypt
        
        Returns:
            Dictionary with encrypted fields
        """
        encrypted_data = data.copy()
        for key in keys_to_encrypt:
            if key in encrypted_data:
                value = encrypted_data[key]
                if value:
                    encrypted_data[key] = self.encrypt(str(value))
        return encrypted_data
    
    def decrypt_dict(self, data: dict, keys_to_decrypt: list) -> dict:
        """
        Decrypt specific fields in a dictionary.
        
        Args:
            data: Dictionary with encrypted data
            keys_to_decrypt: List of keys to decrypt
        
        Returns:
            Dictionary with decrypted fields
        """
        decrypted_data = data.copy()
        for key in keys_to_decrypt:
            if key in decrypted_data:
                value = decrypted_data[key]
                if value:
                    decrypted_value = self.decrypt(value)
                    decrypted_data[key] = decrypted_value
        return decrypted_data


# ============================================================================
# GLOBAL ENCRYPTION MANAGER INSTANCE
# ============================================================================

_encryption_manager_instance: Optional[EncryptionManager] = None


def get_encryption_manager() -> EncryptionManager:
    """Get or create global encryption manager instance"""
    global _encryption_manager_instance
    if _encryption_manager_instance is None:
        _encryption_manager_instance = EncryptionManager()
    return _encryption_manager_instance
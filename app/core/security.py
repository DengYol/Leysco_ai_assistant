"""
app/core/security.py
=====================
Security utilities for token handling
"""

import base64
import hashlib
import hmac
from typing import Optional
import logging
import re
logger = logging.getLogger(__name__)


def mask_token(token: str, show_chars: int = 8) -> str:
    """
    Mask a token for logging/debugging.
    Never logs full tokens.
    
    Args:
        token: The token to mask
        show_chars: Number of characters to show at start and end
    
    Returns:
        Masked token string
    """
    if not token:
        return "***EMPTY***"
    
    if len(token) <= show_chars * 2:
        return "***MASKED***"
    
    return f"{token[:show_chars]}...{token[-show_chars:]}"


def validate_token_structure(token: str) -> bool:
    """
    Basic structural validation of JWT token.
    
    Args:
        token: The token to validate
    
    Returns:
        True if token has valid JWT structure
    """
    # JWT has 3 parts separated by dots
    parts = token.split('.')
    if len(parts) != 3:
        logger.debug(f"Invalid JWT structure: {len(parts)} parts")
        return False
    
    # Each part should be base64url encoded
    for part in parts:
        # Check for valid base64url characters
        if not re.match(r'^[A-Za-z0-9_-]+$', part):
            logger.debug("Invalid base64url encoding in JWT part")
            return False
    
    return True


class TokenValidator:
    """JWT token validator (basic structure only - actual validation by Leysco)"""
    
    @staticmethod
    def validate(token: str) -> bool:
        """Validate token structure"""
        return validate_token_structure(token)
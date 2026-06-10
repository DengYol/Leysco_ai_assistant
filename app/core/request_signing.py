"""
app/core/request_signing.py
===========================

Request signing and integrity verification system.

Features:
  - HMAC-SHA256 request signing
  - Request body integrity checking
  - Timestamp validation (replay attack prevention)
  - Nonce tracking
  - Signature verification

Usage:
  from app.core.request_signing import RequestSigner, get_request_signer
  
  signer = get_request_signer()
  
  # Sign request
  signature = signer.sign_request(
      method="POST",
      path="/api/orders",
      body="{'total': 1000}",
      timestamp=1234567890
  )
  
  # Verify request
  valid = signer.verify_signature(
      method="POST",
      path="/api/orders",
      body="{'total': 1000}",
      signature=signature,
      timestamp=1234567890
  )
"""

import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Set
import os

logger = logging.getLogger(__name__)


# ============================================================================
# REQUEST SIGNER
# ============================================================================

class RequestSigner:
    """
    Request signing and integrity verification.
    
    Prevents request tampering and replay attacks.
    """
    
    def __init__(self):
        """Initialize request signer"""
        self.secret_key = os.getenv(
            "REQUEST_SIGNING_KEY",
            "your-request-signing-key-change-in-production"
        )
        self.timestamp_tolerance = int(os.getenv("REQUEST_TIMESTAMP_TOLERANCE_SECONDS", 300))
        self.max_timestamp_age = int(os.getenv("REQUEST_MAX_TIMESTAMP_AGE_SECONDS", 3600))
        
        # In-memory nonce cache (use Redis in production)
        self.used_nonces: Set[str] = set()
        
        logger.info("✅ RequestSigner initialized")
        logger.info(f"   - Timestamp tolerance: {self.timestamp_tolerance}s")
        logger.info(f"   - Max timestamp age: {self.max_timestamp_age}s")
    
    def sign_request(
        self,
        method: str,
        path: str,
        body: str = "",
        timestamp: Optional[int] = None,
        nonce: Optional[str] = None,
    ) -> str:
        """
        Sign a request.
        
        Args:
            method: HTTP method (GET, POST, etc)
            path: Request path
            body: Request body
            timestamp: Unix timestamp (current time if None)
            nonce: Unique nonce for replay protection
        
        Returns:
            HMAC-SHA256 signature
        """
        if timestamp is None:
            timestamp = int(datetime.utcnow().timestamp())
        
        # Create signature payload
        payload = f"{method}|{path}|{body}|{timestamp}"
        if nonce:
            payload += f"|{nonce}"
        
        # Sign with HMAC-SHA256
        signature = hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        logger.debug(f"Request signed: {method} {path}")
        return signature
    
    def verify_signature(
        self,
        method: str,
        path: str,
        body: str = "",
        signature: str = "",
        timestamp: Optional[int] = None,
        nonce: Optional[str] = None,
    ) -> bool:
        """
        Verify request signature.
        
        Args:
            method: HTTP method
            path: Request path
            body: Request body
            signature: Signature to verify
            timestamp: Request timestamp
            nonce: Request nonce
        
        Returns:
            True if signature is valid
        """
        if not signature or not timestamp:
            logger.warning("Missing signature or timestamp")
            return False
        
        # Verify timestamp is recent
        now = int(datetime.utcnow().timestamp())
        if abs(now - timestamp) > self.max_timestamp_age:
            logger.warning(f"Timestamp too old: {timestamp} vs {now}")
            return False
        
        # Check nonce (replay attack prevention)
        if nonce:
            if nonce in self.used_nonces:
                logger.warning(f"Nonce already used: {nonce}")
                return False
            self.used_nonces.add(nonce)
        
        # Verify signature
        expected_signature = self.sign_request(
            method=method,
            path=path,
            body=body,
            timestamp=timestamp,
            nonce=nonce,
        )
        
        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning(f"Invalid signature for {method} {path}")
            return False
        
        logger.debug(f"Request signature verified: {method} {path}")
        return True
    
    def cleanup_old_nonces(self):
        """Remove old nonces from cache"""
        # In production, implement with Redis expiration
        logger.debug(f"Nonce cache size: {len(self.used_nonces)}")


# ============================================================================
# GLOBAL REQUEST SIGNER INSTANCE
# ============================================================================

_request_signer_instance: Optional[RequestSigner] = None


def get_request_signer() -> RequestSigner:
    """Get or create global request signer instance"""
    global _request_signer_instance
    if _request_signer_instance is None:
        _request_signer_instance = RequestSigner()
    return _request_signer_instance
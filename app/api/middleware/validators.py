"""
app/api/middleware/validators.py
=================================

Request validation middleware for input sanitization.

This middleware:
  1. Validates all request data using Pydantic schemas
  2. Sanitizes inputs to prevent SQL injection, XSS
  3. Rejects malformed requests with clear errors
  4. Logs validation failures for security monitoring

Usage in main.py:
  from app.api.middleware.validators import validation_error_handler
  from fastapi.exceptions import RequestValidationError
  
  app.add_exception_handler(RequestValidationError, validation_error_handler)
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import logging
import json
from datetime import datetime
import re

logger = logging.getLogger(__name__)


# ============================================================================
# VALIDATION ERROR HANDLER
# ============================================================================

async def validation_error_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors with safe, informative responses.
    
    Security measures:
    - Never expose internal details
    - Log all validation failures
    - Return generic error to user
    - Include only field names (not values) in response
    """
    
    # Extract validation errors
    errors = exc.errors()
    
    # Log the full error for debugging (server-side only)
    logger.warning(
        f"Validation error on {request.method} {request.url.path}: "
        f"{len(errors)} validation error(s)",
        extra={"ip": request.client.host if request.client else "unknown"}
    )
    
    # Build user-friendly error response (safe to expose)
    error_details = []
    for error in errors:
        error_details.append({
            "field": ".".join(str(x) for x in error["loc"][1:]),  # Skip 'body'
            "message": error["msg"],
            "type": error["type"],
        })
    
    # Log suspicious patterns
    for error in errors:
        msg = error.get("msg", "").lower()
        if any(pattern in msg for pattern in ["sql", "injection", "script", "xss"]):
            logger.critical(
                f"Potential attack detected: {error['msg']} on field {error['loc']}",
                extra={"ip": request.client.host if request.client else "unknown"}
            )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "validation_error",
            "message": "Request validation failed",
            "error_count": len(error_details),
            "errors": error_details,
            "timestamp": datetime.now().isoformat(),
        },
    )


# ============================================================================
# INPUT SANITIZATION UTILITIES
# ============================================================================

class InputSanitizer:
    """Utilities for sanitizing user input"""
    
    # SQL injection patterns to block
    SQL_INJECTION_PATTERNS = [
        r'--\s*$',           # SQL comment
        r'/\*.*\*/',         # SQL multi-line comment
        r'xp_',              # SQL Server extended stored procedure
        r'sp_',              # SQL Server system stored procedure
        r';\s*drop',         # DROP command
        r';\s*delete',       # DELETE command
        r';\s*update',       # UPDATE command
        r';\s*insert',       # INSERT command
        r'union\s+select',   # UNION-based injection
        r'or\s+1\s*=\s*1',   # Classic OR injection
        r"'\s*or\s*'",       # Quote-based injection
    ]
    
    # XSS patterns to block
    XSS_PATTERNS = [
        r'<script',
        r'javascript:',
        r'on\w+\s*=',        # Event handlers (onclick, onload, etc)
        r'<iframe',
        r'<embed',
        r'<object',
    ]
    
    @staticmethod
    def sanitize_string(value: str, allow_special_chars: bool = False) -> str:
        """
        Sanitize a string value.
        
        Args:
            value: String to sanitize
            allow_special_chars: If True, allow common special chars (., -, @)
        
        Returns:
            Sanitized string
        """
        if not isinstance(value, str):
            return value
        
        # Remove null bytes (never safe)
        value = value.replace('\x00', '')
        
        # Strip leading/trailing whitespace
        value = value.strip()
        
        # Check for SQL injection patterns (case-insensitive)
        for pattern in InputSanitizer.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"SQL injection pattern detected: {pattern}")
                raise ValueError(f"Invalid input detected")
        
        # Check for XSS patterns
        for pattern in InputSanitizer.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"XSS pattern detected: {pattern}")
                raise ValueError(f"Invalid input detected")
        
        return value
    
    @staticmethod
    def sanitize_json_dict(data: dict, max_depth: int = 10) -> dict:
        """
        Recursively sanitize all string values in a dictionary.
        
        Args:
            data: Dictionary to sanitize
            max_depth: Maximum nesting depth to prevent DoS
        
        Returns:
            Sanitized dictionary
        """
        if max_depth <= 0:
            raise ValueError("Input nesting too deep")
        
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            # Sanitize key
            if isinstance(key, str):
                key = InputSanitizer.sanitize_string(key)
            
            # Sanitize value
            if isinstance(value, str):
                sanitized[key] = InputSanitizer.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = InputSanitizer.sanitize_json_dict(value, max_depth - 1)
            elif isinstance(value, list):
                sanitized[key] = InputSanitizer.sanitize_json_list(value, max_depth - 1)
            else:
                sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def sanitize_json_list(data: list, max_depth: int = 10) -> list:
        """
        Recursively sanitize all string values in a list.
        
        Args:
            data: List to sanitize
            max_depth: Maximum nesting depth to prevent DoS
        
        Returns:
            Sanitized list
        """
        if max_depth <= 0:
            raise ValueError("Input nesting too deep")
        
        if not isinstance(data, list):
            return data
        
        sanitized = []
        for item in data:
            if isinstance(item, str):
                sanitized.append(InputSanitizer.sanitize_string(item))
            elif isinstance(item, dict):
                sanitized.append(InputSanitizer.sanitize_json_dict(item, max_depth - 1))
            elif isinstance(item, list):
                sanitized.append(InputSanitizer.sanitize_json_list(item, max_depth - 1))
            else:
                sanitized.append(item)
        
        return sanitized


# ============================================================================
# REQUEST SIZE LIMIT CHECK
# ============================================================================

class RequestSizeValidator:
    """Prevent extremely large requests (DoS protection)"""
    
    # Maximum request size: 10MB
    MAX_BODY_SIZE = 10 * 1024 * 1024
    
    @staticmethod
    async def check_content_length(request: Request) -> bool:
        """
        Check if request exceeds maximum size.
        
        Returns:
            True if request is within limits
        """
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > RequestSizeValidator.MAX_BODY_SIZE:
            logger.warning(
                f"Request exceeds maximum size: {content_length} bytes",
                extra={"ip": request.client.host if request.client else "unknown"}
            )
            return False
        return True


# ============================================================================
# LOGGING
# ============================================================================

def log_validation_event(event_type: str, details: dict):
    """
    Log validation-related events for security monitoring.
    
    Args:
        event_type: Type of validation event (success, failure, blocked, etc)
        details: Event details (field, pattern, etc)
    """
    logger.info(
        f"Validation event: {event_type}",
        extra={
            "event_type": event_type,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
    )
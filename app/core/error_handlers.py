"""
app/core/error_handlers.py
==========================

Secure error handling and logging system.

Features:
  - Graceful error handling (no stack traces to users)
  - Secure logging (no passwords/tokens/secrets in logs)
  - Error categorization (client vs server errors)
  - Security event logging (attacks, failures)
  - Structured logging for analytics

Usage:
  from app.core.error_handlers import (
      AppError, ClientError, ServerError,
      handle_exception, log_security_event
  )
  
  @app.exception_handler(Exception)
  async def global_exception_handler(request, exc):
      return await handle_exception(request, exc)
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from datetime import datetime
import logging
import traceback
import re
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# ERROR CLASSES
# ============================================================================

class ErrorSeverity(Enum):
    """Severity levels for errors"""
    LOW = "low"           # User error, no action needed
    MEDIUM = "medium"     # Service degradation
    HIGH = "high"         # Service unavailable
    CRITICAL = "critical" # Security breach risk


class AppError(Exception):
    """Base application error"""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.severity = severity
        self.details = details or {}
        super().__init__(self.message)


class ClientError(AppError):
    """Client-side error (4xx)"""
    
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "CLIENT_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            severity=ErrorSeverity.LOW,
            details=details,
        )


class ServerError(AppError):
    """Server-side error (5xx)"""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "SERVER_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            severity=ErrorSeverity.HIGH,
            details=details,
        )


class AuthenticationError(ClientError):
    """Authentication failed (401)"""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_FAILED",
        )


class AuthorizationError(ClientError):
    """Authorization failed (403)"""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="AUTH_DENIED",
        )


class NotFoundError(ClientError):
    """Resource not found (404)"""
    
    def __init__(self, resource: str = "Resource"):
        super().__init__(
            message=f"{resource} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
        )


class ConflictError(ClientError):
    """Conflict/duplicate error (409)"""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
        )


class RateLimitError(ClientError):
    """Rate limit exceeded (429)"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Too many requests",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMITED",
        )
        self.retry_after = retry_after


class ValidationError(ClientError):
    """Validation error (422)"""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_FAILED",
            details=details or {},
        )


class DatabaseError(ServerError):
    """Database error (500)"""
    
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DATABASE_ERROR",
        )


class ExternalServiceError(ServerError):
    """External service error (502/503)"""
    
    def __init__(self, service: str, message: str = None):
        super().__init__(
            message=message or f"{service} is unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="SERVICE_UNAVAILABLE",
        )


# ============================================================================
# SECURE LOGGING
# ============================================================================

class SecureLogger:
    """Logger that removes sensitive data before logging"""
    
    # Patterns for sensitive data
    SENSITIVE_PATTERNS = [
        (r'password["\']?\s*[:=]\s*["\']?[^"\'\s]+', '***REDACTED***'),
        (r'token["\']?\s*[:=]\s*["\']?[^"\'\s]+', '***REDACTED***'),
        (r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s]+', '***REDACTED***'),
        (r'secret["\']?\s*[:=]\s*["\']?[^"\'\s]+', '***REDACTED***'),
        (r'authorization["\']?\s*[:=]\s*["\']?Bearer\s+[^"\'\s]+', 'Bearer ***REDACTED***'),
        (r'\b\d{16}\b', '****'),  # Credit card numbers
        (r'\b\d{3}-\d{2}-\d{4}\b', '***-**-****'),  # SSN
    ]
    
    @staticmethod
    def redact(text: str) -> str:
        """Remove sensitive data from log text"""
        if not isinstance(text, str):
            return str(text)
        
        for pattern, replacement in SecureLogger.SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text
    
    @staticmethod
    def log_safe(level: str, message: str, extra: Dict = None):
        """Log a message with sensitive data redacted"""
        safe_message = SecureLogger.redact(message)
        safe_extra = {}
        
        if extra:
            for key, value in extra.items():
                if isinstance(value, str):
                    safe_extra[key] = SecureLogger.redact(value)
                else:
                    safe_extra[key] = value
        
        log_func = getattr(logger, level.lower())
        if safe_extra:
            log_func(safe_message, extra=safe_extra)
        else:
            log_func(safe_message)


# ============================================================================
# ERROR RESPONSE BUILDER
# ============================================================================

class ErrorResponse:
    """Build consistent error responses"""
    
    @staticmethod
    def build(
        error: Exception,
        request: Request = None,
        include_details: bool = False,
    ) -> Dict[str, Any]:
        """
        Build error response from exception.
        
        Args:
            error: Exception that occurred
            request: FastAPI request object (optional)
            include_details: Include error details (for debugging)
        
        Returns:
            Dictionary ready to send as JSON response
        """
        
        # Extract error info
        if isinstance(error, AppError):
            status_code = error.status_code
            error_code = error.error_code
            message = error.message
            details = error.details if include_details else None
        else:
            status_code = 500
            error_code = "INTERNAL_ERROR"
            message = "An unexpected error occurred"
            details = None
        
        response = {
            "status": "error",
            "error_code": error_code,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Add request context if available
        if request:
            response["request_id"] = getattr(request, "id", None)
            response["path"] = request.url.path
            response["method"] = request.method
        
        # Add details if requested and available
        if include_details and details:
            response["details"] = details
        
        return response


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

async def handle_exception(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for all unhandled exceptions.
    
    Features:
    - Converts exceptions to safe JSON responses
    - Logs full error (server-side) without exposing to user
    - No stack traces sent to client
    - Security event logging for suspicious errors
    """
    
    # Log full error server-side (includes stack trace)
    logger.error(
        f"Unhandled exception: {type(exc).__name__}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method,
            "ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
        }
    )
    
    # Determine error type and status code
    if isinstance(exc, AppError):
        status_code = exc.status_code
        response_data = ErrorResponse.build(exc, request)
    elif isinstance(exc, ValueError):
        status_code = 400
        response_data = {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid input",
            "timestamp": datetime.now().isoformat(),
        }
    elif isinstance(exc, KeyError):
        status_code = 404
        response_data = {
            "status": "error",
            "error_code": "NOT_FOUND",
            "message": "Resource not found",
            "timestamp": datetime.now().isoformat(),
        }
    else:
        # Unknown error - return generic message
        status_code = 500
        response_data = {
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat(),
        }
        
        # Check for potential security issues
        error_str = str(exc).lower()
        if any(keyword in error_str for keyword in ["sql", "database", "password"]):
            log_security_event(
                event_type="potential_data_leak",
                severity="critical",
                details={
                    "path": request.url.path,
                    "error_type": type(exc).__name__,
                },
            )
    
    return JSONResponse(
        status_code=status_code,
        content=response_data,
    )


async def handle_auth_error(request: Request, exc: AuthenticationError) -> JSONResponse:
    """Handle authentication errors"""
    SecureLogger.log_safe(
        "warning",
        f"Authentication failed",
        extra={
            "path": request.url.path,
            "ip": request.client.host if request.client else "unknown",
        }
    )
    
    response = ErrorResponse.build(exc, request)
    return JSONResponse(
        status_code=exc.status_code,
        content=response,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def handle_rate_limit_error(request: Request, exc: RateLimitError) -> JSONResponse:
    """Handle rate limit errors"""
    log_security_event(
        event_type="rate_limit_exceeded",
        severity="low",
        details={
            "ip": request.client.host if request.client else "unknown",
            "path": request.url.path,
        },
    )
    
    response = ErrorResponse.build(exc, request)
    return JSONResponse(
        status_code=exc.status_code,
        content=response,
        headers={
            "Retry-After": str(exc.retry_after),
            "X-RateLimit-Reset": str(exc.retry_after),
        },
    )


# ============================================================================
# SECURITY EVENT LOGGING
# ============================================================================

def log_security_event(
    event_type: str,
    severity: str = "medium",
    details: Dict[str, Any] = None,
):
    """
    Log security-related events for monitoring and analysis.
    
    Args:
        event_type: Type of security event (auth_failed, rate_limited, injection_attempt, etc)
        severity: low | medium | high | critical
        details: Event details
    """
    
    log_entry = {
        "event_type": event_type,
        "severity": severity,
        "timestamp": datetime.now().isoformat(),
    }
    
    if details:
        log_entry.update(details)
    
    # Log at appropriate level
    if severity == "critical":
        logger.critical(f"SECURITY EVENT: {event_type}", extra=log_entry)
    elif severity == "high":
        logger.error(f"SECURITY EVENT: {event_type}", extra=log_entry)
    else:
        logger.warning(f"SECURITY EVENT: {event_type}", extra=log_entry)


# ============================================================================
# REQUEST/RESPONSE LOGGING
# ============================================================================

async def log_request(request: Request):
    """Log incoming request (without sensitive data)"""
    path = request.url.path
    method = request.method
    ip = request.client.host if request.client else "unknown"
    
    # Don't log sensitive endpoints in detail
    if "login" not in path and "password" not in path:
        logger.debug(
            f"{method} {path}",
            extra={"ip": ip, "user_agent": request.headers.get("user-agent")},
        )


def log_response(status_code: int, method: str, path: str, duration_ms: float):
    """Log response"""
    level = "info"
    if status_code >= 500:
        level = "error"
    elif status_code >= 400:
        level = "warning"
    
    logger.log(
        getattr(logging, level.upper()),
        f"{method} {path} {status_code}",
        extra={"status_code": status_code, "duration_ms": duration_ms},
    )


# ============================================================================
# ERROR RECOVERY SUGGESTIONS
# ============================================================================

def get_recovery_suggestion(error: Exception) -> Optional[str]:
    """Get user-friendly recovery suggestion for common errors"""
    
    error_type = type(error).__name__
    error_msg = str(error).lower()
    
    suggestions = {
        "ConnectionError": "The service is temporarily unavailable. Please try again in a few moments.",
        "TimeoutError": "The request took too long. Please try again.",
        "PermissionError": "You don't have permission to access this resource. Contact support if you believe this is an error.",
        "FileNotFoundError": "The requested resource was not found. Please verify your request.",
        "ValueError": "The provided data is invalid. Please check your input and try again.",
        "DatabaseError": "A database error occurred. Our team has been notified. Please try again later.",
    }
    
    if error_type in suggestions:
        return suggestions[error_type]
    
    # Check for keywords in error message
    if "database" in error_msg or "postgres" in error_msg:
        return "A database error occurred. Please try again later."
    elif "timeout" in error_msg:
        return "The request took too long. Please try again."
    elif "permission" in error_msg or "denied" in error_msg:
        return "You don't have permission to perform this action."
    
    return None
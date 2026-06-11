"""
app/core/security_headers.py
=============================

Security headers middleware for HTTP response hardening.

Features:
  - HSTS (HTTP Strict Transport Security)
  - Content-Type-Options (prevent MIME-type sniffing)
  - XSS Protection headers
  - Clickjacking protection (X-Frame-Options)
  - CSP (Content Security Policy)
  - Referrer Policy
  - Permissions Policy
  - Feature Policy

Usage:
  from app.core.security_headers import add_security_headers
  
  app = FastAPI()
  add_security_headers(app)
"""

from fastapi import FastAPI, Request
from fastapi.responses import Response
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# SECURITY HEADERS
# ============================================================================

SECURITY_HEADERS = {
    # Strict Transport Security - Force HTTPS
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    
    # Prevent MIME-type sniffing (e.g., script execution in <img> tags)
    "X-Content-Type-Options": "nosniff",
    
    # Clickjacking protection - prevent embedding in iframes
    "X-Frame-Options": "DENY",
    
    # XSS Protection (legacy, but still useful)
    "X-XSS-Protection": "1; mode=block",
    
    # Referrer Policy - limit referrer information leakage
    "Referrer-Policy": "strict-origin-when-cross-origin",
    
    # Permissions Policy - restrict access to browser APIs
    "Permissions-Policy": (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "payment=(), "
        "usb=(), "
        "magnetometer=(), "
        "gyroscope=(), "
        "accelerometer=(), "
        "ambient-light-sensor=()"
    ),
    
    # Content Security Policy - prevent XSS and injection attacks
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    
    # Remove Server header (information disclosure)
    "Server": "LeyS AI",
    
    # Enable DNS prefetching (performance)
    "X-DNS-Prefetch-Control": "on",
    
    # Disable caching for sensitive responses
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


# ============================================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================================

async def security_headers_middleware(request: Request, call_next):
    """
    Add security headers to all responses.
    
    Applied to all routes except:
    - Swagger UI (/docs, /redoc)
    - Static files (/static)
    """
    
    # Skip security headers for Swagger and static files
    # (they have their own CSP allowances)
    swagger_paths = ["/docs", "/redoc", "/openapi.json", "/static"]
    skip_csp = any(request.url.path.startswith(p) for p in swagger_paths)
    
    response = await call_next(request)
    
    # Add security headers
    for header, value in SECURITY_HEADERS.items():
        # Skip CSP for Swagger (it needs inline scripts)
        if skip_csp and header == "Content-Security-Policy":
            response.headers[header] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https: wss:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            response.headers[header] = value
    
    return response


# ============================================================================
# ADD SECURITY HEADERS TO APP
# ============================================================================

def add_security_headers(app: FastAPI):
    """
    Register security headers middleware with FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    app.middleware("http")(security_headers_middleware)
    logger.info("✅ Security headers middleware registered")
    logger.info("   - HSTS (HTTP Strict Transport Security): ENABLED")
    logger.info("   - Clickjacking protection (X-Frame-Options): ENABLED")
    logger.info("   - MIME-type sniffing protection: ENABLED")
    logger.info("   - XSS Protection: ENABLED")
    logger.info("   - Content Security Policy: ENABLED")
    logger.info("   - Referrer Policy: ENABLED")
    logger.info("   - Permissions Policy: ENABLED")
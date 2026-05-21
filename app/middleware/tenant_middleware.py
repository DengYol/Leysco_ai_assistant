"""
app/middleware/tenant_middleware.py
====================================
Middleware for tenant context setup
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, List
import logging

from app.core.tenant_context import TenantContext, set_current_tenant, clear_current_tenant
from app.services.leysco_api.client import LeyscoAPIService

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract tenant information from token.
    
    This middleware:
    1. Extracts the Bearer token from Authorization header
    2. Calls Leysco API to validate token and get tenant info
    3. Sets tenant context for the request
    4. Cleans up after request
    """
    
    # Public endpoints that don't require authentication
    PUBLIC_ENDPOINTS: List[str] = [
        "/health",
        "/api/auth/login", 
        "/docs",
        "/openapi.json",
        "/redoc",
        "/",
        "/ping"
    ]
    
    async def dispatch(self, request: Request, call_next):
        # Skip tenant resolution for public endpoints
        if request.url.path in self.PUBLIC_ENDPOINTS:
            logger.debug(f"Skipping tenant middleware for public endpoint: {request.url.path}")
            return await call_next(request)
        
        # Extract headers
        auth_header = request.headers.get("Authorization")
        company_code_header = request.headers.get("X-Company-Code")
        
        # If no auth header, proceed without tenant context (but log warning)
        if not auth_header:
            logger.warning(f"No Authorization header for {request.url.path} - proceeding without tenant context")
            return await call_next(request)
        
        try:
            # Parse Bearer token
            parts = auth_header.split()
            if len(parts) != 2:
                logger.warning(f"Invalid Authorization header format: expected 'Bearer <token>'")
                return await self._unauthorized_response("Invalid authorization header format")
            
            scheme, token = parts
            if scheme.lower() != 'bearer':
                logger.warning(f"Invalid auth scheme: {scheme} (expected 'bearer')")
                return await self._unauthorized_response("Invalid authentication scheme")
            
            # Validate token structure
            if not token or len(token) < 10:
                logger.warning(f"Invalid token format: too short ({len(token)} chars)")
                return await self._unauthorized_response("Invalid token format")
            
            # Mask token for logging (security)
            masked = self._mask_token(token)
            logger.debug(f"Processing request with token: {masked}")
            
            # Create API service with user token for validation
            api_service = LeyscoAPIService(user_token=token)
            
            # Validate token and get user/tenant info
            # This calls Leysco API to verify the token and get tenant context
            validation_result = await api_service.validate_token()
            
            if not validation_result:
                logger.error(f"Token validation returned no result for {masked}")
                return await self._unauthorized_response("Unable to validate token")
            
            if not validation_result.get("valid"):
                logger.warning(f"Token validation failed for {masked}: {validation_result.get('error', 'Unknown error')}")
                return await self._unauthorized_response("Invalid or expired token")
            
            # Extract tenant info from validation result
            company_code = validation_result.get("company_code")
            if not company_code:
                logger.error(f"Validation result missing company_code for {masked}")
                return await self._unauthorized_response("Invalid token: missing company information")
            
            # Verify company code matches header if provided
            if company_code_header and company_code_header.upper() != company_code.upper():
                logger.warning(f"Company code mismatch: header={company_code_header}, token={company_code}")
                return await self._unauthorized_response("Company code does not match token")
            
            # Create tenant context
            tenant = TenantContext(
                company_code=company_code.upper(),
                company_id=validation_result.get("company_id", 0),
                user_id=validation_result.get("user_id", 0),
                user_email=validation_result.get("email", ""),
                user_role=validation_result.get("role", "user"),
                user_token=token  # Pass through for API calls
            )
            
            # Set context for this request
            set_current_tenant(tenant)
            logger.info(f"✅ Tenant context set: {tenant.company_code} (User: {tenant.user_id}, Role: {tenant.user_role})")
            
            # Add tenant info to request state for easy access in endpoints
            request.state.tenant = tenant
            request.state.user_token = token
            
            # Process the request
            response = await call_next(request)
            return response
            
        except ValueError as e:
            logger.warning(f"Auth header parsing error: {e}")
            return await self._unauthorized_response("Invalid authorization header")
        
        except Exception as e:
            logger.error(f"Tenant middleware error: {e}", exc_info=True)
            return await self._unauthorized_response("Authentication failed")
        
        finally:
            # Clean up tenant context
            clear_current_tenant()
            logger.debug("Tenant context cleared")
    
    async def _unauthorized_response(self, detail: str) -> JSONResponse:
        """Return 401 Unauthorized response"""
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={"detail": detail, "status": "error"},
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    @staticmethod
    def _mask_token(token: str, show_chars: int = 8) -> str:
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


# Import for type hint
from fastapi.responses import JSONResponse
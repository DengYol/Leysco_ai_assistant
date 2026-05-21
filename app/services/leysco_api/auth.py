"""Authentication and token management for Leysco API Service"""

import logging
from typing import Dict, Optional
from requests import Session, RequestException

logger = logging.getLogger(__name__)


class AuthHandler:
    """Handles authentication and token validation"""
    
    def __init__(self, session: Session, base_url: str, timeout: int = 30):
        self.session = session
        self.base_url = base_url
        self.timeout = timeout
        self.user_token: Optional[str] = None
        self._is_authenticated: bool = False
        self._stats = {"auth_errors": 0}
    
    def set_user_token(self, token: str):
        """Update user token for this instance"""
        self.user_token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self._is_authenticated = True
        logger.debug("User token updated")
    
    def ensure_auth(self) -> bool:
        """Ensure we have valid authentication (token present)"""
        if not self.user_token:
            logger.warning("No user token available for API call")
            return False
        return True
    
    def check_auth(self, response) -> bool:
        """Check if response indicates authentication failure"""
        if response.status_code == 401:
            self._stats["auth_errors"] += 1
            logger.warning(f"Authentication failed (401) - token may be invalid or expired")
            self._is_authenticated = False
            return False
        
        if response.status_code == 302:
            self._stats["auth_errors"] += 1
            logger.warning(f"Authentication redirect (302) - possible session expiry")
            self._is_authenticated = False
            return False
        
        return True
    
    def is_authenticated(self) -> bool:
        """Return current authentication status"""
        return self._is_authenticated and bool(self.user_token)
    
    async def validate_token(self) -> Optional[Dict]:
        """
        Validate the current user token with Leysco API.
        Returns user and tenant information if valid.
        """
        if not self.user_token:
            logger.error("Cannot validate token - no token provided")
            return {"valid": False, "error": "No token provided"}
        
        try:
            url = f"{self.base_url}/auth/validate"
            resp = self.session.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("valid") or data.get("ResultState"):
                    logger.info(f"✅ Token validated successfully")
                    return {
                        "valid": True,
                        "user_id": data.get("user_id") or data.get("id"),
                        "email": data.get("email"),
                        "role": data.get("role") or data.get("user_role", "user"),
                        "company_code": data.get("company_code") or data.get("tenant_code"),
                        "company_id": data.get("company_id") or data.get("tenant_id", 0)
                    }
            
            logger.warning(f"Token validation failed: HTTP {resp.status_code}")
            return {"valid": False, "error": f"HTTP {resp.status_code}"}
            
        except RequestException as e:
            logger.error(f"Token validation request error: {e}")
            return {"valid": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return {"valid": False, "error": str(e)}
    
    def login(self, username: str, password: str) -> bool:
        """
        Authenticate with the API and store token.
        NOTE: This is for system-level authentication only.
        """
        try:
            url = f"{self.base_url}/auth/login"
            payload = {"username": username, "password": password}
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token") or data.get("access_token")
                if token:
                    self.user_token = token
                    self.session.headers.update({"Authorization": f"Bearer {token}"})
                    self._is_authenticated = True
                    logger.info("✅ Successfully authenticated with CRM")
                    return True
            logger.error(f"❌ Login failed: {resp.status_code}")
            self._is_authenticated = False
            return False
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            self._is_authenticated = False
            return False
    
    def get_auth_stats(self) -> Dict:
        """Get authentication statistics"""
        return self._stats.copy()
"""
app/core/rbac.py
================

Role-Based Access Control (RBAC) system.

Features:
  - User roles (admin, manager, sales_rep, etc)
  - Permission-based access control
  - Resource-level permissions
  - Action-level permissions
  - Role hierarchy

Usage:
  from app.core.rbac import RBAC, get_rbac
  
  rbac = get_rbac()
  
  # Check if user can perform action
  can_delete = rbac.can_user(
      user_id=123,
      role="sales_rep",
      action="delete_order",
      resource="orders"
  )
"""

from enum import Enum
from typing import Set, Dict, List, Optional
from functools import wraps
from fastapi import HTTPException, status, Request
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# ROLES
# ============================================================================

class UserRole(Enum):
    """User roles"""
    ADMIN = "admin"              # System administrator
    MANAGER = "manager"          # Sales manager
    SALES_REP = "sales_rep"      # Sales representative
    CUSTOMER = "customer"        # Customer user
    VIEWER = "viewer"            # Read-only access


# ============================================================================
# PERMISSIONS
# ============================================================================

class Permission(Enum):
    """Available permissions"""
    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_LIST = "user:list"
    
    # Order management
    ORDER_CREATE = "order:create"
    ORDER_READ = "order:read"
    ORDER_UPDATE = "order:update"
    ORDER_DELETE = "order:delete"
    ORDER_LIST = "order:list"
    
    # Customer management
    CUSTOMER_CREATE = "customer:create"
    CUSTOMER_READ = "customer:read"
    CUSTOMER_UPDATE = "customer:update"
    CUSTOMER_DELETE = "customer:delete"
    CUSTOMER_LIST = "customer:list"
    
    # Inventory management
    INVENTORY_READ = "inventory:read"
    INVENTORY_UPDATE = "inventory:update"
    INVENTORY_LIST = "inventory:list"
    
    # Analytics & Reports
    ANALYTICS_READ = "analytics:read"
    ANALYTICS_EXPORT = "analytics:export"
    
    # Admin functions
    ADMIN_CONFIG = "admin:config"
    ADMIN_AUDIT = "admin:audit"
    ADMIN_USERS = "admin:users"


# ============================================================================
# RBAC SYSTEM
# ============================================================================

class RBAC:
    """
    Role-Based Access Control system.
    
    Manages user roles and permissions.
    """
    
    def __init__(self):
        """Initialize RBAC"""
        self.role_permissions = self._init_role_permissions()
        logger.info("✅ RBAC initialized")
    
    def _init_role_permissions(self) -> Dict[str, Set[str]]:
        """Initialize role -> permissions mapping"""
        return {
            UserRole.ADMIN.value: {
                # Admin has all permissions
                "user:create", "user:read", "user:update", "user:delete", "user:list",
                "order:create", "order:read", "order:update", "order:delete", "order:list",
                "customer:create", "customer:read", "customer:update", "customer:delete", "customer:list",
                "inventory:read", "inventory:update", "inventory:list",
                "analytics:read", "analytics:export",
                "admin:config", "admin:audit", "admin:users",
            },
            UserRole.MANAGER.value: {
                # Manager can read/update most things
                "user:read", "user:list",
                "order:create", "order:read", "order:update", "order:list",
                "customer:read", "customer:update", "customer:list",
                "inventory:read", "inventory:update", "inventory:list",
                "analytics:read", "analytics:export",
            },
            UserRole.SALES_REP.value: {
                # Sales rep can create and manage orders/customers
                "order:create", "order:read", "order:update", "order:list",
                "customer:read", "customer:update", "customer:list",
                "inventory:read", "inventory:list",
                "analytics:read",
            },
            UserRole.CUSTOMER.value: {
                # Customer can read their own data
                "order:read", "order:list",
                "customer:read",
                "analytics:read",
            },
            UserRole.VIEWER.value: {
                # Viewer has read-only access
                "order:read", "order:list",
                "customer:read", "customer:list",
                "inventory:read", "inventory:list",
                "analytics:read",
            },
        }
    
    def has_permission(self, role: str, permission: str) -> bool:
        """
        Check if role has permission.
        
        Args:
            role: User role (e.g., "admin", "sales_rep")
            permission: Permission to check (e.g., "order:create")
        
        Returns:
            True if role has permission
        """
        permissions = self.role_permissions.get(role, set())
        return permission in permissions
    
    def can_user(
        self,
        role: str,
        action: str,
        resource: str = None,
    ) -> bool:
        """
        Check if user can perform action on resource.
        
        Args:
            role: User role
            action: Action (create, read, update, delete)
            resource: Resource type (optional, for specificity)
        
        Returns:
            True if user can perform action
        """
        # Build permission string
        if resource:
            permission = f"{resource}:{action}"
        else:
            permission = action
        
        return self.has_permission(role, permission)
    
    def get_role_permissions(self, role: str) -> Set[str]:
        """Get all permissions for a role"""
        return self.role_permissions.get(role, set())
    
    def get_user_resources(self, role: str) -> Set[str]:
        """Get resources accessible by role"""
        permissions = self.get_role_permissions(role)
        resources = set()
        for perm in permissions:
            if ":" in perm:
                resource = perm.split(":")[0]
                resources.add(resource)
        return resources


# ============================================================================
# DECORATORS FOR PERMISSION CHECKING
# ============================================================================

def require_permission(permission: str):
    """
    Decorator to require specific permission.
    
    Usage:
        @app.post("/orders")
        @require_permission("order:create")
        async def create_order(request: Request, data: OrderData):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            if not request:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Request object required"
                )
            
            # Get user role from request state
            user_role = getattr(request.state, "user_role", None)
            if not user_role:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User role not found in request"
                )
            
            # Check permission
            rbac = get_rbac()
            if not rbac.has_permission(user_role, permission):
                logger.warning(
                    f"Permission denied: {user_role} attempting {permission}",
                    extra={"user_role": user_role, "permission": permission}
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission}"
                )
            
            return await func(*args, request=request, **kwargs)
        
        return wrapper
    return decorator


def require_role(*allowed_roles: str):
    """
    Decorator to require specific role.
    
    Usage:
        @app.post("/admin/config")
        @require_role("admin")
        async def update_config(request: Request, data: ConfigData):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            if not request:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Request object required"
                )
            
            user_role = getattr(request.state, "user_role", None)
            if not user_role:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User role not found"
                )
            
            if user_role not in allowed_roles:
                logger.warning(
                    f"Insufficient role: {user_role} not in {allowed_roles}",
                    extra={"user_role": user_role, "required_roles": allowed_roles}
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This operation requires one of: {', '.join(allowed_roles)}"
                )
            
            return await func(*args, request=request, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# GLOBAL RBAC INSTANCE
# ============================================================================

_rbac_instance: Optional[RBAC] = None


def get_rbac() -> RBAC:
    """Get or create global RBAC instance"""
    global _rbac_instance
    if _rbac_instance is None:
        _rbac_instance = RBAC()
    return _rbac_instance
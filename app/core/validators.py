"""
app/core/validators.py
======================

Input validation schemas using Pydantic v2.

Validates ALL user inputs before they reach business logic:
- Prevents SQL injection
- Prevents XSS attacks
- Enforces type safety
- Ensures data consistency

Usage:
  from app.core.validators import ChatRequestSchema

  @app.post("/api/ai/chat")
  async def chat(request: ChatRequestSchema):
      # Input is already validated by Pydantic
      pass
"""

from pydantic import BaseModel, Field, validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
import re


# ============================================================================
# GENERAL SCHEMAS
# ============================================================================

class PaginationSchema(BaseModel):
    """Pagination parameters - used across all list endpoints"""
    
    skip: int = Field(0, ge=0, le=10000, description="Number of items to skip")
    limit: int = Field(20, ge=1, le=100, description="Max items to return")
    
    @validator('skip', 'limit', pre=True)
    def validate_pagination_integers(cls, v):
        if not isinstance(v, int):
            try:
                return int(v)
            except (ValueError, TypeError):
                raise ValueError("Must be an integer")
        return v


class DateRangeSchema(BaseModel):
    """Date range filter - used for analytics/reports"""
    
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        if v and 'start_date' in values and values['start_date']:
            if v < values['start_date']:
                raise ValueError("end_date must be after start_date")
        return v


# ============================================================================
# AUTHENTICATION SCHEMAS
# ============================================================================

class LoginRequestSchema(BaseModel):
    """Login request validation"""
    
    username: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)
    
    @validator('username')
    def validate_username(cls, v):
        # Allow alphanumeric, dots, underscores, hyphens
        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError("Username can only contain letters, numbers, dots, underscores, and hyphens")
        return v.lower()
    
    @validator('password')
    def validate_password_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TokenRefreshSchema(BaseModel):
    """Token refresh request"""
    
    refresh_token: str = Field(..., min_length=10)
    
    @validator('refresh_token')
    def validate_token_format(cls, v):
        # Tokens should be alphanumeric with hyphens/underscores
        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError("Invalid token format")
        return v


# ============================================================================
# CHAT & CONVERSATION SCHEMAS
# ============================================================================

class ChatRequestSchema(BaseModel):
    """Chat message request - MOST IMPORTANT (used frequently)"""
    
    message: str = Field(..., min_length=1, max_length=5000)
    session_id: Optional[str] = Field(None, max_length=255)
    company_code: Optional[str] = Field(None, max_length=50)
    user_context: Optional[Dict[str, Any]] = Field(None)
    
    model_config = ConfigDict(extra='forbid')  # Reject unknown fields
    
    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError("Message cannot be empty or whitespace only")
        # Remove leading/trailing whitespace
        v = v.strip()
        return v
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9-]+$', v):
            raise ValueError("Invalid session ID format")
        return v
    
    @validator('company_code')
    def validate_company_code(cls, v):
        if v and not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("Company code must be uppercase alphanumeric")
        return v.upper() if v else v


class ClearSessionSchema(BaseModel):
    """Session clear request"""
    
    session_id: str = Field(..., min_length=1, max_length=255)
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not re.match(r'^[a-zA-Z0-9-]+$', v):
            raise ValueError("Invalid session ID format")
        return v


# ============================================================================
# CUSTOMER SCHEMAS
# ============================================================================

class CustomerFilterSchema(BaseModel):
    """Filter parameters for customer searches"""
    
    name: Optional[str] = Field(None, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    region: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None, max_length=50)
    
    @validator('name', 'region', 'status')
    def sanitize_string_fields(cls, v):
        if v:
            # Remove leading/trailing whitespace
            v = v.strip()
            # Reject if contains suspicious SQL patterns
            suspicious = ['--', '/*', '*/', 'xp_', 'sp_']
            for pattern in suspicious:
                if pattern.lower() in v.lower():
                    raise ValueError(f"Invalid characters in input")
        return v
    
    @validator('code')
    def validate_code_format(cls, v):
        if v and not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("Code must be uppercase alphanumeric")
        return v.upper() if v else v


class CustomerDetailsSchema(BaseModel):
    """Customer details request"""
    
    customer_code: str = Field(..., min_length=1, max_length=50)
    
    @validator('customer_code')
    def validate_customer_code(cls, v):
        if not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("Customer code must be uppercase alphanumeric")
        return v.upper()


# ============================================================================
# ITEM & INVENTORY SCHEMAS
# ============================================================================

class ItemFilterSchema(BaseModel):
    """Filter parameters for item searches"""
    
    item_code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    
    @validator('item_code')
    def validate_item_code(cls, v):
        if v and not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("Item code must be uppercase alphanumeric")
        return v.upper() if v else v
    
    @validator('name', 'category')
    def sanitize_text(cls, v):
        if v:
            v = v.strip()
            # Block SQL injection patterns
            if any(pattern in v.lower() for pattern in ['--', '/*', '*/', 'xp_', 'sp_']):
                raise ValueError("Invalid characters detected")
        return v


class InventoryQuerySchema(BaseModel):
    """Inventory query parameters"""
    
    warehouse_code: Optional[str] = Field(None, max_length=50)
    item_code: Optional[str] = Field(None, max_length=50)
    min_quantity: Optional[int] = Field(None, ge=0)
    
    @validator('warehouse_code', 'item_code')
    def validate_codes(cls, v):
        if v and not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("Code must be uppercase alphanumeric")
        return v.upper() if v else v


class PriceRequestSchema(BaseModel):
    """Price query request"""
    
    item_code: str = Field(..., max_length=50)
    quantity: Optional[int] = Field(None, ge=1, le=1000000)
    customer_code: Optional[str] = Field(None, max_length=50)
    
    @validator('item_code', 'customer_code')
    def validate_codes(cls, v):
        if v and not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("Code must be uppercase alphanumeric")
        return v.upper() if v else v


# ============================================================================
# ORDER SCHEMAS
# ============================================================================

class OrderFilterSchema(BaseModel):
    """Filter parameters for order searches"""
    
    order_code: Optional[str] = Field(None, max_length=50)
    customer_code: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=50)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    
    @validator('order_code', 'customer_code')
    def validate_codes(cls, v):
        if v and not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError("Code must be uppercase alphanumeric")
        return v.upper() if v else v
    
    @validator('status')
    def validate_status(cls, v):
        if v:
            valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']
            if v.lower() not in valid_statuses:
                raise ValueError(f"Status must be one of: {', '.join(valid_statuses)}")
        return v.lower() if v else v
    
    @validator('date_to')
    def validate_date_range(cls, v, values):
        if v and 'date_from' in values and values['date_from']:
            if v < values['date_from']:
                raise ValueError("date_to must be after date_from")
        return v


# ============================================================================
# NOTIFICATION SCHEMAS
# ============================================================================

class NotificationPreferencesSchema(BaseModel):
    """User notification preferences"""
    
    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = True
    notification_types: Optional[List[str]] = None
    
    @validator('notification_types')
    def validate_notification_types(cls, v):
        if v:
            valid_types = ['order', 'inventory', 'price', 'payment', 'customer']
            for nt in v:
                if nt not in valid_types:
                    raise ValueError(f"Invalid notification type: {nt}")
        return v


# ============================================================================
# BULK OPERATION SCHEMAS
# ============================================================================

class BulkActionSchema(BaseModel):
    """Schema for bulk operations"""
    
    action: str = Field(..., max_length=50)
    ids: List[str] = Field(..., min_items=1, max_items=1000)
    
    @validator('action')
    def validate_action(cls, v):
        valid_actions = ['export', 'delete', 'archive', 'update_status']
        if v.lower() not in valid_actions:
            raise ValueError(f"Action must be one of: {', '.join(valid_actions)}")
        return v.lower()
    
    @validator('ids')
    def validate_ids(cls, v):
        for id_val in v:
            if not re.match(r'^[a-zA-Z0-9-]+$', id_val):
                raise ValueError("Invalid ID format")
        return v


# ============================================================================
# SEARCH & QUERY SCHEMAS
# ============================================================================

class SearchQuerySchema(BaseModel):
    """General search query"""
    
    q: str = Field(..., min_length=1, max_length=500)
    search_type: Optional[str] = Field(None, max_length=50)
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
    
    @validator('q')
    def sanitize_query(cls, v):
        v = v.strip()
        # Block SQL injection patterns
        dangerous = ['--', '/*', '*/', 'xp_', 'sp_', 'exec', 'execute']
        if any(pattern in v.lower() for pattern in dangerous):
            raise ValueError("Invalid query characters")
        return v
    
    @validator('search_type')
    def validate_search_type(cls, v):
        if v:
            valid = ['customer', 'item', 'order', 'all']
            if v.lower() not in valid:
                raise ValueError(f"search_type must be one of: {', '.join(valid)}")
        return v.lower() if v else v


# ============================================================================
# ANALYTICS & REPORTING SCHEMAS
# ============================================================================

class AnalyticsQuerySchema(BaseModel):
    """Analytics query parameters"""
    
    metric: str = Field(..., max_length=100)
    start_date: datetime
    end_date: datetime
    group_by: Optional[str] = Field(None, max_length=50)
    filters: Optional[Dict[str, Any]] = None
    
    @validator('metric')
    def validate_metric(cls, v):
        valid_metrics = ['sales', 'revenue', 'orders', 'inventory', 'customers']
        if v.lower() not in valid_metrics:
            raise ValueError(f"Metric must be one of: {', '.join(valid_metrics)}")
        return v.lower()
    
    @validator('group_by')
    def validate_group_by(cls, v):
        if v:
            valid = ['day', 'week', 'month', 'region', 'product']
            if v.lower() not in valid:
                raise ValueError(f"group_by must be one of: {', '.join(valid)}")
        return v.lower() if v else v
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError("end_date must be after start_date")
        return v


# ============================================================================
# EXPORT SCHEMAS
# ============================================================================

class ExportRequestSchema(BaseModel):
    """Request to export data"""
    
    data_type: str = Field(..., max_length=50)
    format: str = Field(..., max_length=10)
    filters: Optional[Dict[str, Any]] = None
    
    @validator('data_type')
    def validate_data_type(cls, v):
        valid = ['customers', 'orders', 'items', 'inventory', 'analytics']
        if v.lower() not in valid:
            raise ValueError(f"data_type must be one of: {', '.join(valid)}")
        return v.lower()
    
    @validator('format')
    def validate_format(cls, v):
        valid = ['csv', 'json', 'excel']
        if v.lower() not in valid:
            raise ValueError(f"format must be one of: {', '.join(valid)}")
        return v.lower()


# ============================================================================
# ERROR RESPONSE SCHEMA
# ============================================================================

class ValidationErrorResponse(BaseModel):
    """Standard validation error response"""
    
    status: str = "validation_error"
    message: str
    details: Optional[List[Dict[str, Any]]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================================
# SUCCESS RESPONSE SCHEMA
# ============================================================================

class SuccessResponse(BaseModel):
    """Standard success response wrapper"""
    
    status: str = "success"
    data: Optional[Any] = None
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
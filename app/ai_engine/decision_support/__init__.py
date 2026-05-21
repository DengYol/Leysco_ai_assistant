"""Decision Support Module - Business intelligence and analytics"""

from .client import DecisionSupport, get_decision_support
from .constants import THRESHOLDS, CACHE_TTL
from .utils import (
    mean, std_dev, sqrt, confidence_score,
    get_health_rating, get_rfm_segment
)

__all__ = [
    'DecisionSupport',
    'get_decision_support',
    'THRESHOLDS',
    'CACHE_TTL',
    'mean',
    'std_dev',
    'sqrt',
    'confidence_score',
    'get_health_rating',
    'get_rfm_segment'
]
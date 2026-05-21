"""Base formatter for LLM data formatting"""

from abc import ABC, abstractmethod
from typing import Any, List, Dict


class BaseFormatter(ABC):
    """Abstract base class for data formatters"""
    
    @abstractmethod
    def format(self, data: Any, language: str = "en") -> str:
        """Format data for LLM consumption"""
        pass
    
    def _safe_float(self, value, default: float = 0.0) -> float:
        """Safely convert to float"""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _safe_str(self, value, default: str = "") -> str:
        """Safely convert to string"""
        if value is None:
            return default
        return str(value)
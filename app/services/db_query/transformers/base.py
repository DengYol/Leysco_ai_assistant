"""Base transformer with common methods"""

from typing import List, Dict, Any


class BaseTransformer:
    """Base class for all transformers"""
    
    @staticmethod
    def add_summary_if_truncated(data: List[Dict], original_count: int, max_items: int, 
                                  extra_summary: Dict = None) -> List[Dict]:
        """Add summary entry if data was truncated."""
        if original_count <= max_items:
            return data
        
        summary = {
            "_summary": True,
            "total": original_count,
            "displayed": max_items,
            "message": f"Showing {max_items} of {original_count} items."
        }
        if extra_summary:
            summary.update(extra_summary)
        
        data.append(summary)
        return data
    
    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert to float."""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def safe_str(value: Any, default: str = "") -> str:
        """Safely convert to string."""
        if value is None:
            return default
        return str(value)
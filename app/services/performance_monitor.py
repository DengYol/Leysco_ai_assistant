"""
performance_monitor.py
======================
Performance monitoring service for tracking request times and system health.
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
import json

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Tracks performance metrics for API requests and system operations.
    
    Features:
    - Request timing tracking
    - Endpoint latency monitoring
    - Error rate tracking
    - Cache hit/miss tracking
    - Memory usage monitoring (optional)
    - Periodic cleanup of old metrics
    """
    
    def __init__(self, max_history_minutes: int = 60, cleanup_interval_seconds: int = 300):
        """
        Initialize the performance monitor.
        
        Args:
            max_history_minutes: Maximum minutes to keep metrics history
            cleanup_interval_seconds: How often to clean up old metrics
        """
        self.max_history_minutes = max_history_minutes
        self.cleanup_interval_seconds = cleanup_interval_seconds
        
        # Metrics storage
        self._request_times: Dict[str, List[float]] = defaultdict(list)  # endpoint -> list of times (ms)
        self._request_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._cache_hits: Dict[str, int] = defaultdict(int)
        self._cache_misses: Dict[str, int] = defaultdict(int)
        self._timestamps: Dict[str, List[datetime]] = defaultdict(list)  # track when requests happened
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Start cleanup thread
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        
        logger.info(f"✅ PerformanceMonitor initialized (history: {max_history_minutes} minutes)")
    
    # =========================================================
    # REQUEST TRACKING
    # =========================================================
    
    def track_request(self, endpoint: str, duration_ms: float) -> None:
        """
        Track a request duration.
        
        Args:
            endpoint: The endpoint being called (e.g., "chat", "dashboard")
            duration_ms: Request duration in milliseconds
        """
        with self._lock:
            self._request_times[endpoint].append(duration_ms)
            self._request_counts[endpoint] += 1
            self._timestamps[endpoint].append(datetime.now())
    
    def track_error(self, endpoint: str) -> None:
        """
        Track an error occurrence.
        
        Args:
            endpoint: The endpoint where the error occurred
        """
        with self._lock:
            self._error_counts[endpoint] += 1
    
    def track_cache_hit(self, endpoint: str) -> None:
        """Track a cache hit."""
        with self._lock:
            self._cache_hits[endpoint] += 1
    
    def track_cache_miss(self, endpoint: str) -> None:
        """Track a cache miss."""
        with self._lock:
            self._cache_misses[endpoint] += 1
    
    # =========================================================
    # METRICS RETRIEVAL
    # =========================================================
    
    def get_metrics(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Args:
            endpoint: Specific endpoint to get metrics for, or None for all
        
        Returns:
            Dictionary with performance metrics
        """
        with self._lock:
            self._cleanup_old_data()
            
            if endpoint:
                return self._get_endpoint_metrics(endpoint)
            else:
                return self._get_all_metrics()
    
    def _get_endpoint_metrics(self, endpoint: str) -> Dict[str, Any]:
        """Get metrics for a specific endpoint."""
        times = self._request_times.get(endpoint, [])
        request_count = self._request_counts.get(endpoint, 0)
        error_count = self._error_counts.get(endpoint, 0)
        cache_hits = self._cache_hits.get(endpoint, 0)
        cache_misses = self._cache_misses.get(endpoint, 0)
        total_cache = cache_hits + cache_misses
        cache_hit_rate = (cache_hits / total_cache * 100) if total_cache > 0 else 0
        
        metrics = {
            "endpoint": endpoint,
            "total_requests": request_count,
            "errors": error_count,
            "error_rate": (error_count / request_count * 100) if request_count > 0 else 0,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": round(cache_hit_rate, 1),
        }
        
        # Add timing metrics if there are requests
        if times:
            sorted_times = sorted(times)
            metrics.update({
                "avg_response_time_ms": round(sum(times) / len(times), 2),
                "min_response_time_ms": round(min(times), 2),
                "max_response_time_ms": round(max(times), 2),
                "p50_response_time_ms": round(sorted_times[len(times) // 2], 2),
                "p95_response_time_ms": round(sorted_times[int(len(times) * 0.95)], 2) if len(times) > 1 else round(max(times), 2),
                "p99_response_time_ms": round(sorted_times[int(len(times) * 0.99)], 2) if len(times) > 1 else round(max(times), 2),
            })
        
        return metrics
    
    def _get_all_metrics(self) -> Dict[str, Any]:
        """Get metrics for all endpoints."""
        with self._lock:
            endpoints = set(self._request_counts.keys()) | set(self._error_counts.keys())
            
            all_metrics = {}
            total_requests = 0
            total_errors = 0
            all_times = []
            
            for endpoint in endpoints:
                metrics = self._get_endpoint_metrics(endpoint)
                all_metrics[endpoint] = metrics
                total_requests += metrics.get("total_requests", 0)
                total_errors += metrics.get("errors", 0)
                if "avg_response_time_ms" in metrics:
                    all_times.extend(self._request_times.get(endpoint, []))
            
            # Summary metrics
            summary = {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "overall_error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0,
            }
            
            if all_times:
                sorted_times = sorted(all_times)
                summary.update({
                    "overall_avg_response_time_ms": round(sum(all_times) / len(all_times), 2),
                    "overall_min_response_time_ms": round(min(all_times), 2),
                    "overall_max_response_time_ms": round(max(all_times), 2),
                    "overall_p50_response_time_ms": round(sorted_times[len(all_times) // 2], 2),
                    "overall_p95_response_time_ms": round(sorted_times[int(len(all_times) * 0.95)], 2),
                })
            
            return {
                "endpoints": all_metrics,
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }
    
    # =========================================================
    # REAL-TIME MONITORING
    # =========================================================
    
    def get_recent_metrics(self, minutes: int = 5) -> Dict[str, Any]:
        """
        Get metrics for recent requests (last N minutes).
        
        Args:
            minutes: Number of minutes to look back
        
        Returns:
            Dictionary with recent metrics
        """
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        with self._lock:
            recent_counts: Dict[str, int] = defaultdict(int)
            recent_times: Dict[str, List[float]] = defaultdict(list)
            recent_errors: Dict[str, int] = defaultdict(int)
            
            for endpoint, timestamps in self._timestamps.items():
                for i, ts in enumerate(timestamps):
                    if ts >= cutoff:
                        recent_counts[endpoint] += 1
                        if i < len(self._request_times.get(endpoint, [])):
                            recent_times[endpoint].append(self._request_times[endpoint][i])
                
                # Count recent errors (we need to track errors with timestamps as well)
                # For simplicity, use the same cutoff for errors
                # In production, you'd want to store error timestamps separately
        
        # Build response
        endpoints = set(recent_counts.keys())
        recent_metrics = {}
        
        for endpoint in endpoints:
            times = recent_times.get(endpoint, [])
            metrics = {
                "requests": recent_counts[endpoint],
                "errors": recent_errors.get(endpoint, 0),
            }
            
            if times:
                metrics.update({
                    "avg_ms": round(sum(times) / len(times), 2),
                    "min_ms": round(min(times), 2),
                    "max_ms": round(max(times), 2),
                })
            
            recent_metrics[endpoint] = metrics
        
        return {
            "period_minutes": minutes,
            "cutoff_time": cutoff.isoformat(),
            "metrics": recent_metrics,
            "total_requests": sum(recent_counts.values())
        }
    
    # =========================================================
    # HEALTH CHECK
    # =========================================================
    
    def health_check(self) -> Dict[str, Any]:
        """
        Get system health status.
        
        Returns:
            Dictionary with health status
        """
        metrics = self.get_metrics()
        total_requests = metrics["summary"].get("total_requests", 0)
        error_rate = metrics["summary"].get("overall_error_rate", 0)
        avg_response = metrics["summary"].get("overall_avg_response_time_ms", 0)
        
        # Determine health status
        if error_rate > 10:
            status = "critical"
            status_message = "High error rate detected"
        elif error_rate > 5:
            status = "warning"
            status_message = "Elevated error rate"
        elif avg_response > 3000:
            status = "warning"
            status_message = "Slow response times"
        elif total_requests == 0:
            status = "unknown"
            status_message = "No requests recorded"
        else:
            status = "healthy"
            status_message = "System operating normally"
        
        return {
            "status": status,
            "message": status_message,
            "total_requests": total_requests,
            "error_rate": round(error_rate, 1),
            "avg_response_time_ms": round(avg_response, 2),
            "timestamp": datetime.now().isoformat()
        }
    
    # =========================================================
    # CLEANUP
    # =========================================================
    
    def _cleanup_old_data(self) -> None:
        """Remove data older than max_history_minutes."""
        cutoff = datetime.now() - timedelta(minutes=self.max_history_minutes)
        
        with self._lock:
            for endpoint in list(self._timestamps.keys()):
                timestamps = self._timestamps[endpoint]
                times = self._request_times.get(endpoint, [])
                
                # Find indices to keep
                keep_indices = [i for i, ts in enumerate(timestamps) if ts >= cutoff]
                
                if not keep_indices:
                    # All data is old - clear everything for this endpoint
                    self._timestamps.pop(endpoint, None)
                    self._request_times.pop(endpoint, None)
                    # Don't clear counts completely - they are cumulative
                else:
                    # Keep only recent data
                    self._timestamps[endpoint] = [timestamps[i] for i in keep_indices]
                    if times:
                        self._request_times[endpoint] = [times[i] for i in keep_indices if i < len(times)]
    
    def _cleanup_worker(self) -> None:
        """Background thread for periodic cleanup."""
        while not self._stop_cleanup.wait(self.cleanup_interval_seconds):
            try:
                self._cleanup_old_data()
            except Exception as e:
                logger.error(f"Performance monitor cleanup error: {e}")
    
    def stop(self) -> None:
        """Stop the cleanup thread."""
        self._stop_cleanup.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        logger.info("Performance monitor stopped")
    
    # =========================================================
    # RESET
    # =========================================================
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._request_times.clear()
            self._request_counts.clear()
            self._error_counts.clear()
            self._cache_hits.clear()
            self._cache_misses.clear()
            self._timestamps.clear()
        logger.info("Performance monitor metrics reset")
    
    # =========================================================
    # FORMATTED OUTPUT
    # =========================================================
    
    def get_formatted_report(self) -> str:
        """
        Get a human-readable performance report.
        
        Returns:
            Formatted string with performance metrics
        """
        metrics = self.get_metrics()
        summary = metrics.get("summary", {})
        
        lines = [
            "📊 **Performance Report**",
            f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "**Summary:**",
            f"• Total Requests: {summary.get('total_requests', 0)}",
            f"• Error Rate: {summary.get('overall_error_rate', 0):.1f}%",
            f"• Avg Response: {summary.get('overall_avg_response_time_ms', 0):.0f} ms",
            f"• P95 Response: {summary.get('overall_p95_response_time_ms', 0):.0f} ms",
            "",
            "**Endpoint Details:**",
        ]
        
        for endpoint, data in metrics.get("endpoints", {}).items():
            lines.append(f"\n**{endpoint}:**")
            lines.append(f"  • Requests: {data.get('total_requests', 0)}")
            lines.append(f"  • Errors: {data.get('errors', 0)}")
            lines.append(f"  • Error Rate: {data.get('error_rate', 0):.1f}%")
            lines.append(f"  • Cache Hit Rate: {data.get('cache_hit_rate', 0):.1f}%")
            
            if "avg_response_time_ms" in data:
                lines.append(f"  • Avg: {data['avg_response_time_ms']:.0f} ms")
                lines.append(f"  • P95: {data['p95_response_time_ms']:.0f} ms")
        
        return "\n".join(lines)


# Global instance
performance_monitor = PerformanceMonitor()
import time
import functools
import logging
from typing import Dict, Any, Callable
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Performance monitoring utility for tracking execution times and metrics"""
    
    def __init__(self):
        self.metrics = {}
    
    @contextmanager
    def timer(self, operation_name: str):
        """Context manager for timing operations"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.record_metric(operation_name, duration)
            logger.info(f"{operation_name} took {duration:.2f} seconds")
    
    def record_metric(self, name: str, value: float):
        """Record a performance metric"""
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(value)
    
    def get_stats(self, name: str) -> Dict[str, float]:
        """Get statistics for a metric"""
        if name not in self.metrics:
            return {}
        
        values = self.metrics[name]
        return {
            'count': len(values),
            'total': sum(values),
            'avg': sum(values) / len(values),
            'min': min(values),
            'max': max(values)
        }
    
    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Get all performance statistics"""
        return {name: self.get_stats(name) for name in self.metrics.keys()}

def performance_monitor(operation_name: str):
    """Decorator for monitoring function performance"""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                logger.info(f"{operation_name} ({func.__name__}) took {duration:.2f} seconds")
        return wrapper
    return decorator

# Global performance monitor instance
perf_monitor = PerformanceMonitor()

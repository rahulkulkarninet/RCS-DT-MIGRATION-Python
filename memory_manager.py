import gc
import psutil
import pandas as pd
from typing import Optional, Dict, Any
import logging

class MemoryManager:
    """Manage memory usage during data processing operations."""
    
    def __init__(self, max_memory_percent: float = 85.0):
        self.max_memory_percent = max_memory_percent
        self.logger = logging.getLogger(__name__)
        
    def get_memory_usage(self) -> float:
        """Get current memory usage percentage."""
        return psutil.virtual_memory().percent
    
    def check_memory_limit(self) -> bool:
        """Check if memory usage is below threshold."""
        usage = self.get_memory_usage()
        if usage > self.max_memory_percent:
            self.logger.warning(f"Memory usage high: {usage:.1f}%")
            return False
        return True
    
    def cleanup_dataframe(self, df: Optional[pd.DataFrame]) -> None:
        """Safely cleanup DataFrame and force garbage collection."""
        if df is not None:
            try:
                del df
                gc.collect()
                self.logger.debug("DataFrame cleaned up")
            except Exception as e:
                self.logger.warning(f"Error cleaning DataFrame: {e}")
    
    def process_with_memory_check(self, process_func, *args, **kwargs):
        """Execute function with memory monitoring."""
        memory_before = self.get_memory_usage()
        
        try:
            result = process_func(*args, **kwargs)
            memory_after = self.get_memory_usage()
            
            self.logger.info(f"Memory: {memory_before:.1f}% → {memory_after:.1f}%")
            
            if memory_after > self.max_memory_percent:
                self.logger.warning("Memory threshold exceeded, forcing cleanup")
                gc.collect()
                
            return result
            
        except MemoryError:
            self.logger.error("Out of memory during processing")
            gc.collect()
            raise
"""
Caching module for QA validation operations
Provides file-based caching with TTL support
"""

import json
import hashlib
import pickle
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


class NPICache:
    """
    File-based cache for NPI lookups with TTL (Time To Live).
    
    Caches both direct NPI lookups and fuzzy search results to reduce
    external API calls to NPPES registry.
    """
    
    def __init__(self, cache_dir: str = ".cache", ttl_days: int = 30):
        """
        Initialize NPI cache.
        
        Args:
            cache_dir: Directory to store cache files
            ttl_days: Number of days before cache entries expire
        """
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "npi_cache.pkl")
        self.ttl = timedelta(days=ttl_days)
        self.cache = self._load_cache()
        self.hits = 0
        self.misses = 0
    
    def _load_cache(self) -> Dict:
        """Load cache from disk"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Warning: Failed to load NPI cache: {e}")
                return {}
        return {}
    
    def _save_cache(self):
        """Save cache to disk"""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            print(f"Warning: Failed to save NPI cache: {e}")
    
    def _is_expired(self, timestamp: datetime) -> bool:
        """Check if cache entry has expired"""
        return datetime.now() - timestamp > self.ttl
    
    def get_npi_lookup(self, npi: str) -> Optional[Dict]:
        """
        Get cached NPI lookup result.
        
        Args:
            npi: NPI number to lookup
            
        Returns:
            Cached result dict or None if not found/expired
        """
        key = f"npi_lookup:{npi}"
        
        if key in self.cache:
            data, timestamp = self.cache[key]
            if not self._is_expired(timestamp):
                self.hits += 1
                return data
            else:
                # Remove expired entry
                del self.cache[key]
                self._save_cache()
        
        self.misses += 1
        return None
    
    def set_npi_lookup(self, npi: str, data: Dict):
        """
        Cache NPI lookup result.
        
        Args:
            npi: NPI number
            data: Lookup result to cache
        """
        key = f"npi_lookup:{npi}"
        self.cache[key] = (data, datetime.now())
        self._save_cache()
    
    def get_fuzzy_search(self, physician_name: str, address: str, city: str, state: str) -> Optional[Dict]:
        """
        Get cached fuzzy search result.
        
        Args:
            physician_name: Physician name
            address: Address
            city: City
            state: State
            
        Returns:
            Cached result dict or None if not found/expired
        """
        # Create unique key from search parameters
        search_params = f"{physician_name}|{address}|{city}|{state}".lower()
        key = f"fuzzy_search:{hashlib.md5(search_params.encode()).hexdigest()}"
        
        if key in self.cache:
            data, timestamp = self.cache[key]
            if not self._is_expired(timestamp):
                self.hits += 1
                return data
            else:
                # Remove expired entry
                del self.cache[key]
                self._save_cache()
        
        self.misses += 1
        return None
    
    def set_fuzzy_search(self, physician_name: str, address: str, city: str, state: str, data: Dict):
        """
        Cache fuzzy search result.
        
        Args:
            physician_name: Physician name
            address: Address
            city: City
            state: State
            data: Search result to cache
        """
        search_params = f"{physician_name}|{address}|{city}|{state}".lower()
        key = f"fuzzy_search:{hashlib.md5(search_params.encode()).hexdigest()}"
        self.cache[key] = (data, datetime.now())
        self._save_cache()
    
    def clear(self):
        """Clear all cache entries"""
        self.cache = {}
        self._save_cache()
        self.hits = 0
        self.misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats (hits, misses, hit_rate, size)
        """
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "total_entries": len(self.cache),
            "cache_file": self.cache_file
        }
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        expired_keys = []
        
        for key, (data, timestamp) in self.cache.items():
            if self._is_expired(timestamp):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            self._save_cache()
        
        return len(expired_keys)


# Global cache instance
_npi_cache = None


def get_npi_cache() -> NPICache:
    """
    Get global NPI cache instance (singleton pattern).
    
    Returns:
        NPICache instance
    """
    global _npi_cache
    if _npi_cache is None:
        _npi_cache = NPICache()
    return _npi_cache

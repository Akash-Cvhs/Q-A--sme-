"""
Utility script to view and manage NPI cache
"""

import sys
import os

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from cache import get_npi_cache


def show_stats():
    """Display cache statistics"""
    cache = get_npi_cache()
    stats = cache.get_stats()
    
    print("=" * 60)
    print("NPI CACHE STATISTICS")
    print("=" * 60)
    print(f"Cache File: {stats['cache_file']}")
    print(f"Total Entries: {stats['total_entries']}")
    print(f"Cache Hits: {stats['hits']}")
    print(f"Cache Misses: {stats['misses']}")
    print(f"Hit Rate: {stats['hit_rate']}")
    print("=" * 60)


def clear_cache():
    """Clear all cache entries"""
    cache = get_npi_cache()
    cache.clear()
    print("Cache cleared successfully!")


def cleanup_expired():
    """Remove expired cache entries"""
    cache = get_npi_cache()
    removed = cache.cleanup_expired()
    print(f"Removed {removed} expired entries")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "stats":
            show_stats()
        elif command == "clear":
            clear_cache()
        elif command == "cleanup":
            cleanup_expired()
        else:
            print("Unknown command. Available commands:")
            print("  stats   - Show cache statistics")
            print("  clear   - Clear all cache entries")
            print("  cleanup - Remove expired entries")
    else:
        show_stats()

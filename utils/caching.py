import json
import logging
import time
from pathlib import Path
import hashlib
import os
from typing import Any, Optional

# Need to import config loader relative to this file's location
try:
    from .config_loader import get_config
except ImportError:
    # Fallback for potential execution as script? Less ideal.
    from config_loader import get_config


# --- Load Cache Configuration ---
try:
    config = get_config()
    CACHE_CONFIG = config.get('cache', {})
    CACHE_ENABLED = CACHE_CONFIG.get('enabled', False)
    # Resolve cache directory relative to project root
    # Assuming config_loader.py correctly identifies project root or this file is utils/caching.py
    PROJECT_ROOT = Path(__file__).parent.parent
    CACHE_DIR_NAME = CACHE_CONFIG.get('directory', 'cache/api_responses')
    CACHE_DIR = PROJECT_ROOT / CACHE_DIR_NAME
    CACHE_TTL = CACHE_CONFIG.get('ttl_seconds', 900) # Default 15 mins
    logging.info(f"Cache Config Loaded: Enabled={CACHE_ENABLED}, Dir={CACHE_DIR}, TTL={CACHE_TTL}")

except Exception as e:
    logging.error(f"Failed to load cache config, disabling cache. Error: {e}")
    CACHE_ENABLED = False
    CACHE_DIR = None
    CACHE_TTL = 0

def _ensure_cache_dir():
    """Ensures the cache directory exists."""
    global CACHE_ENABLED
    if CACHE_ENABLED and CACHE_DIR:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            logging.debug(f"Cache directory ensured: {CACHE_DIR}")
        except OSError as e:
            logging.error(f"Could not create cache directory {CACHE_DIR}: {e}. Disabling cache.")
            CACHE_ENABLED = False
    # else:
        # logging.debug("Cache disabled or directory not set, skipping dir creation.")


# Ensure directory exists on module load if enabled
_ensure_cache_dir()

def _generate_cache_key(*args: Any) -> str:
    """Generates a stable cache key (hash) from input arguments."""
    key_material = "|".join(sorted(map(str, args)))
    return hashlib.sha256(key_material.encode()).hexdigest()[:32]


def get_cached_data(key_args: list[Any]) -> Optional[Any]:
    """
    Retrieves data from cache if it exists and is not expired.
    """
    if not CACHE_ENABLED or not CACHE_DIR:
        # logging.debug("Cache disabled or dir not set, skipping cache read.")
        return None

    cache_key = _generate_cache_key(*key_args)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            # Check file modification time first (slightly cheaper than reading+parsing)
            file_mod_time = cache_file.stat().st_mtime
            if time.time() - file_mod_time < CACHE_TTL:
                logging.debug(f"Cache HIT (by mod time) for key: {cache_key} (args: {key_args})")
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_obj = json.load(f)
                # Optional: secondary check using timestamp stored inside file
                # timestamp = cached_obj.get('timestamp', 0)
                # if time.time() - timestamp < CACHE_TTL:
                #     return cached_obj.get('data')
                # else: # Stored timestamp expired, treat as miss
                #     logging.debug(f"Cache STALE (by internal timestamp) for key: {cache_key}")

                # If mod time check passed, return data
                return cached_obj.get('data')

            else:
                logging.debug(f"Cache EXPIRED (by mod time) for key: {cache_key}")
                # Optionally remove expired file
                # cache_file.unlink(missing_ok=True)

        except (json.JSONDecodeError, IOError, OSError, Exception) as e:
            logging.warning(f"Could not read, decode, or stat cache file {cache_file}: {e}")
            # Optionally remove corrupted file
            try: cache_file.unlink(missing_ok=True)
            except OSError: pass # Ignore error trying to delete potentially non-existent file

    # logging.debug(f"Cache MISS for key: {cache_key} (args: {key_args})")
    return None


def set_cached_data(key_args: list[Any], data: Any):
    """
    Saves data to the cache.
    """
    if not CACHE_ENABLED or not CACHE_DIR:
        # logging.debug("Cache disabled or dir not set, skipping cache write.")
        return

    # Ensure directory exists again (might have failed initially or been deleted)
    _ensure_cache_dir()
    if not CACHE_ENABLED: return # Re-check if dir creation failed

    cache_key = _generate_cache_key(*key_args)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    cache_obj = {
        'timestamp': time.time(),
        'key_args_repr': repr(key_args), # Store args representation for debugging
        'data': data
    }

    try:
        temp_file_path = cache_file.with_suffix('.tmp')
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(cache_obj, f) # Consider indent=2 for debug inspection?
        # Atomic rename (or as close as possible on Windows)
        os.replace(temp_file_path, cache_file)
        logging.debug(f"Cache WRITTEN for key: {cache_key}")
    except (IOError, TypeError, OSError, Exception) as e:
        logging.error(f"Could not write cache file {cache_file}: {e}")
        # Clean up temp file if it exists
        if temp_file_path.exists():
            try: temp_file_path.unlink()
            except OSError: pass


def clear_cache():
    """Removes all *.json files from the cache directory."""
    if not CACHE_ENABLED or not CACHE_DIR or not CACHE_DIR.exists():
        logging.info("Cache is disabled or directory does not exist. Nothing to clear.")
        return

    cleared_count = 0; error_count = 0
    logging.info(f"Clearing cache directory: {CACHE_DIR}")
    try:
        for item in CACHE_DIR.iterdir():
            if item.is_file() and item.suffix == '.json':
                try:
                    item.unlink()
                    cleared_count += 1
                except OSError as e:
                    logging.warning(f"Could not remove cache file {item}: {e}")
                    error_count += 1
        logging.info(f"Cache cleared. Removed {cleared_count} files, failed to remove {error_count} files.")
    except OSError as e:
        logging.error(f"Could not iterate cache directory {CACHE_DIR}: {e}")


# Example Usage
if __name__ == "__main__":
    # Need basic logging setup to see output from this block
    log_format = '%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format)

    print("--- Cache Module Test ---")
    print(f"Cache Enabled: {CACHE_ENABLED}")
    print(f"Cache Directory: {CACHE_DIR}")
    print(f"Cache TTL: {CACHE_TTL} seconds")

    if CACHE_ENABLED:
        test_key1 = ["data1", "paramA", 123]
        test_data1 = {"value": "apple", "count": 5}
        test_key2 = ["data2", "paramB"]
        test_data2 = [1, 2, 3, 4, 5]

        print("\n1. Clearing cache (start fresh)...")
        clear_cache()

        print("\n2. Testing cache miss...")
        cached = get_cached_data(test_key1)
        print(f"   Result: {'Found' if cached else 'Not Found'} -> {cached}")

        print("\n3. Setting cache data...")
        set_cached_data(test_key1, test_data1)
        set_cached_data(test_key2, test_data2)

        print("\n4. Testing cache hit...")
        cached1 = get_cached_data(test_key1)
        cached2 = get_cached_data(test_key2)
        print(f"   Result 1: {'Found' if cached1 else 'Not Found'} -> {cached1}")
        print(f"   Result 2: {'Found' if cached2 else 'Not Found'} -> {cached2}")

        if CACHE_TTL >= 2:
             wait_time = 2 # Wait just 2 seconds for testing expiry quickly
             print(f"\n5. Waiting {wait_time}s...")
             time.sleep(wait_time)
             if CACHE_TTL <= wait_time:
                 print("   (Cache should be expired now)")
                 cached1_after_wait = get_cached_data(test_key1)
                 print(f"   Result 1 after wait: {'Found' if cached1_after_wait else 'Not Found'}")
             else:
                 print("   (Cache should still be valid)")
                 cached1_after_wait = get_cached_data(test_key1)
                 print(f"   Result 1 after wait: {'Found' if cached1_after_wait else 'Not Found'}")

        print("\n6. Clearing cache again...")
        clear_cache()
        cached = get_cached_data(test_key1)
        print(f"   Result after clear: {'Found' if cached else 'Not Found'}")
    else:
        print("\nCache is disabled in configuration. Tests skipped.") 
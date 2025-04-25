import requests
import logging
from datetime import date, timedelta, datetime # Need datetime for history params
import time # For debugging cache timing if needed
from utils.config_loader import get_config
from utils.caching import get_cached_data, set_cached_data

# Configure logging - will be configured by main script based on config
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get API base URL from config
try:
    config = get_config()
    API_CONFIG = config.get('api', {})
    ANALYSIS_CONFIG = config.get('analysis', {}) # Need for history timescale
    BASE_URL = API_CONFIG.get('base_url', "https://default.url/api/v2/stats") # Base URL for both price & history
    BASE_PRICE_URL = f"{BASE_URL}/prices"
    BASE_HISTORY_URL = f"{BASE_URL}/history" # History endpoint URL
    HISTORY_TIME_SCALE = ANALYSIS_CONFIG.get('history_time_scale', 24) # Default 24h

except Exception as e:
    logging.error(f"Failed to load config for API URLs/History, using defaults. Error: {e}")
    BASE_PRICE_URL = "https://old.west.albion-online-data.com/api/v2/stats/prices"
    BASE_HISTORY_URL = "https://old.west.albion-online-data.com/api/v2/stats/history"
    HISTORY_TIME_SCALE = 24


def get_item_prices(item_ids: list[str], locations: list[str] | None = None, qualities: list[int] | None = None) -> list[dict] | None:
    """
    Fetches market price data for specified items from the Albion Online Data Project API.
    Uses the base URL defined in the configuration file.

    Args:
        item_ids: A list of unique item IDs (e.g., ['T4_BAG', 'T5_CAPE']).
        locations: A list of locations (e.g., ['Caerleon', 'Lymhurst']). Defaults to all cities if None.
        qualities: A list of item qualities (1-5). Defaults to all qualities if None.

    Returns:
        A list of dictionaries containing price data for the requested items,
        or None if the request fails.
    """
    if not item_ids:
        logging.error("No item IDs provided.")
        return None

    sorted_items = sorted(item_ids); sorted_locs = sorted(locations) if locations else ["None"]; sorted_quals = sorted(qualities) if qualities else ["None"]
    cache_key_args = ["prices", ",".join(sorted_items), ",".join(sorted_locs), ",".join(map(str, sorted_quals))]
    cached_result = get_cached_data(cache_key_args)
    if cached_result is not None: return cached_result
    logging.info(f"Fetching FRESH prices for items: {item_ids}, locations: {locations}, qualities: {qualities}")
    items_string = ",".join(item_ids)
    params = {}
    if locations:
        params["locations"] = ",".join(locations)
    if qualities:
        params["qualities"] = ",".join(map(str, qualities))

    url = f"{BASE_PRICE_URL}/{items_string}" # Use the configured base URL

    try:
        logging.debug(f"Fetching data from URL: {url} with params: {params}") # Changed to debug
        response = requests.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        set_cached_data(cache_key_args, data) # Cache the result
        logging.debug(f"Successfully fetched data for {len(data)} item/location/quality combinations.") # Changed to debug
        return data

    except requests.exceptions.RequestException as e:
        logging.error(f"API request failed for URL {url}: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during API request: {e}")
        return None

# Example usage removed, should be called from analyzer or main

# --- New Function: get_item_history ---
def get_item_history(item_ids: list[str], locations: list[str], quality: int = 1, date_start: date | None = None) -> list[dict] | None:
    """
    Fetches market history data (including volume) for specified items/locations.

    Args:
        item_ids: A list of unique item IDs.
        locations: A list of locations.
        quality: The specific item quality level (1-5).
        date_start: The start date for the history (YYYY-MM-DD). Defaults to 1 day ago.

    Returns:
        A list of dictionaries containing history data, or None if the request fails.
        Structure includes 'item_count' which represents volume for that period.
    """
    if not item_ids: logging.error("[History] No item IDs provided."); return None
    if not locations: logging.error("[History] No locations provided."); return None

    # Define date range (e.g., last 1 day for recent volume)
    if date_start is None:
        date_start = date.today() - timedelta(days=1)
    # API expects date and end_date, let's just fetch one day for avg volume calc
    date_end = date.today()

    # Format dates and other params
    date_str = date_start.strftime("%Y-%m-%d")
    end_date_str = date_end.strftime("%Y-%m-%d")
    locations_str = ",".join(locations)
    items_string = ",".join(item_ids)

    # --- Cache Check ---
    sorted_items = sorted(item_ids)
    sorted_locs = sorted(locations)
    # Key includes endpoint type, items, locs, quality, date, timescale
    cache_key_args = [
        "history",
        ",".join(sorted_items),
        ",".join(sorted_locs),
        str(quality),
        date_str,
        str(HISTORY_TIME_SCALE)
    ]
    cached_result = get_cached_data(cache_key_args)
    if cached_result is not None:
        logging.debug(f"[History] Cache HIT for key: {cache_key_args}")
        return cached_result
    logging.debug(f"[History] Cache MISS for key: {cache_key_args}")
    # --- End Cache Check ---

    logging.info(f"[History] Fetching FRESH history for items: {items_string[:50]}..., locations: {locations_str}, Q:{quality}, Date:{date_str}, Timescale:{HISTORY_TIME_SCALE}")

    params = {
        "date": date_str,
        "end_date": end_date_str,
        "locations": locations_str,
        "qualities": str(quality),
        "time-scale": str(HISTORY_TIME_SCALE) # Use timescale from config
    }
    url = f"{BASE_HISTORY_URL}/{items_string}"

    try:
        logging.debug(f"[History] Request URL: {url}")
        logging.debug(f"[History] Request params: {params}")
        response = requests.get(url, params=params, timeout=20) # Added timeout
        logging.info(f"[History] API Response Status Code: {response.status_code}") # Log status code
        response.raise_for_status() # Raise HTTPError for bad responses (4XX or 5XX)

        data = response.json()
        # --- Added Logging ---
        logging.debug(f"[History] Successfully fetched {len(data)} raw history data points.")
        if data: logging.debug(f"[History] Sample raw data point: {data[0]}")
        # --- End Logging ---

        set_cached_data(cache_key_args, data) # Cache the result
        return data

    except requests.exceptions.Timeout:
        logging.error(f"[History] API history request timed out for URL {url}")
        return None
    except requests.exceptions.RequestException as e:
        # Log more details about the error if possible
        err_msg = f"[History] API history request failed for URL {url}: {e}"
        if e.response is not None:
            err_msg += f" | Response Status: {e.response.status_code}, Response Body: {e.response.text[:200]}..."
        logging.error(err_msg)
        return None
    except Exception as e:
        logging.error(f"[History] An unexpected error occurred during API history request: {e}", exc_info=True)
        return None


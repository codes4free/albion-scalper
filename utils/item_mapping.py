import requests
import logging
import os
import re
from pathlib import Path
import json # Keep json import
from .config_loader import get_config # Import config loader

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
ITEM_FILE_URL = "https://raw.githubusercontent.com/broderickhyman/ao-bin-dumps/master/formatted/items.json" # <<< New JSON URL
# Store the downloaded file in a 'data' subdirectory within 'utils'
DATA_DIR = Path(__file__).parent / "data"
LOCAL_ITEM_FILE = DATA_DIR / "items.json" # <<< New JSON filename

# --- Data Structures ---
ITEM_ID_TO_NAME: dict[str, str] = {}
ITEM_NAME_TO_ID: dict[str, str] = {}
ITEM_CATEGORIES: dict[str, dict] = {} # Load categories from config
_ITEM_DATA_LOADED = False # Add a flag

# --- Private Functions ---

def _ensure_data_dir():
    """Ensures the data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def _download_item_file(url: str, destination: Path) -> bool:
    """Downloads the item file from the given URL."""
    logging.info(f"Downloading item file from {url} to {destination}...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logging.info("Item file downloaded successfully.")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download item file: {e}")
        return False
    except IOError as e:
        logging.error(f"Failed to write item file to {destination}: {e}")
        return False

def _parse_item_file(file_path: Path):
    """Parses the items.json file and populates mapping dictionaries using only EN-US names."""
    global ITEM_ID_TO_NAME, ITEM_NAME_TO_ID
    logging.info(f"[Parse] Attempting to parse item JSON file (EN-US only): {file_path}")
    ITEM_ID_TO_NAME.clear(); ITEM_NAME_TO_ID.clear()
    items_parsed = 0
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
             logging.error(f"[Parse] Failed: Expected a JSON list, got {type(data)}.")
             return

        for item_data in data:
            if not isinstance(item_data, dict):
                # logging.warning(f"[Parse] Skipping invalid item data entry (not a dict): {item_data}")
                continue

            item_id = item_data.get('UniqueName')
            if not item_id: # Skip if no UniqueName found
                # logging.debug(f"[Parse] Skipping item entry missing 'UniqueName'")
                continue

            # --- Get EN-US name specifically ---
            item_name_en = None
            localized_names = item_data.get('LocalizedNames')
            if isinstance(localized_names, dict):
                item_name_en = localized_names.get('EN-US')

            # Use EN-US name if available, otherwise fall back to the UniqueName itself
            item_name = item_name_en if item_name_en else item_id
            # --- End EN-US specific logic ---

            # if items_parsed < 5: logging.debug(f"[Parse] Parsed: ID='{item_id}', Name='{item_name}'")

            ITEM_ID_TO_NAME[item_id] = item_name
            # Use the final item_name (EN-US or ID) for the reverse mapping
            if item_name not in ITEM_NAME_TO_ID:
                ITEM_NAME_TO_ID[item_name] = item_id
            items_parsed += 1

        logging.info(f"[Parse] Finished parsing JSON (EN-US only). Total items processed: {items_parsed}.")
        if not items_parsed:
             logging.error("[Parse] Parsed 0 items from JSON. Check file content.")

    except FileNotFoundError:
        logging.error(f"[Parse] Item JSON file not found: {file_path}")
    except json.JSONDecodeError as e:
        logging.error(f"[Parse] Error decoding JSON file {file_path}: {e}")
    except IOError as e:
        logging.error(f"[Parse] Error reading item file {file_path}: {e}")
    except Exception as e:
        logging.error(f"[Parse] An unexpected error occurred during JSON parsing: {e}", exc_info=True)


def _load_item_data():
    """Ensures the item data and categories are loaded."""
    global ITEM_CATEGORIES, ITEM_ID_TO_NAME, _ITEM_DATA_LOADED
    if _ITEM_DATA_LOADED:
        logging.debug("[Load] Data already loaded flag is set.")
        return

    logging.info("[Load] Entering _load_item_data...")

    # Load items IF NOT ALREADY LOADED
    if not ITEM_ID_TO_NAME:
        logging.info("[Load] ITEM_ID_TO_NAME is empty, proceeding with load.")
        _ensure_data_dir()
        if not LOCAL_ITEM_FILE.exists():
             logging.info(f"[Load] Local item file {LOCAL_ITEM_FILE} not found, attempting download from {ITEM_FILE_URL}.")
             if not _download_item_file(ITEM_FILE_URL, LOCAL_ITEM_FILE):
                 logging.error("[Load] Download failed. Item mapping unavailable.")
                 ITEM_ID_TO_NAME.clear()
                 ITEM_NAME_TO_ID.clear()
                 return # Exit if download fails
             else:
                 logging.info("[Load] Download successful.")
        else:
            logging.info(f"[Load] Found local item file: {LOCAL_ITEM_FILE}")

        _parse_item_file(LOCAL_ITEM_FILE)
        # --- Added Check ---
        if not ITEM_ID_TO_NAME:
             logging.error("[Load] ITEM_ID_TO_NAME is STILL EMPTY after parsing attempt.")
        else:
             logging.info(f"[Load] ITEM_ID_TO_NAME size after loading: {len(ITEM_ID_TO_NAME)}")
        # --- End Check ---
    else:
        logging.debug("[Load] ITEM_ID_TO_NAME map already populated.")


    # Load categories IF NOT ALREADY LOADED
    if not ITEM_CATEGORIES:
        logging.info("[Load] Item categories map is empty, loading from config.")
        try:
            config = get_config()
            ITEM_CATEGORIES = config.get('item_categories', {})
            logging.info(f"[Load] Loaded {len(ITEM_CATEGORIES)} item categories from config.")
        except Exception as e:
            logging.error(f"[Load] Failed to load item categories from config: {e}")
            ITEM_CATEGORIES = {}
    else:
        logging.debug("[Load] Item categories map already populated.")

    # Set flag only if item data seems successfully loaded
    if ITEM_ID_TO_NAME:
        _ITEM_DATA_LOADED = True
        logging.info("[Load] Setting _ITEM_DATA_LOADED flag to True.")
    else:
         logging.warning("[Load] Not setting _ITEM_DATA_LOADED flag because ITEM_ID_TO_NAME is empty.")

    logging.info("[Load] Exiting _load_item_data.")


# --- Public API ---

def get_item_name(item_id: str) -> str | None:
    """Retrieves the human-readable name for a given item ID."""
    _load_item_data()
    return ITEM_ID_TO_NAME.get(item_id)

def get_item_id(item_name: str) -> str | None:
    """Retrieves the item ID for a given human-readable name."""
    _load_item_data()
    item_id = ITEM_NAME_TO_ID.get(item_name)
    if not item_id:
        # Attempt case-insensitive lookup as a fallback - could be slow with many items
        item_name_lower = item_name.lower()
        for name, iid in ITEM_ID_TO_NAME.items():
             # Consider caching the lower->iid mapping if performance is critical
            if name.lower() == item_name_lower:
                return iid
        # logging.debug(f"Item name not found in mapping: {item_name}")
    return item_id

def get_all_item_ids() -> list[str]:
    """Returns a list of all known item IDs."""
    _load_item_data()
    return list(ITEM_ID_TO_NAME.keys())

def get_all_item_names() -> list[str]:
    """Returns a list of all known item names."""
    _load_item_data()
    return list(ITEM_ID_TO_NAME.values())

def get_item_ids_by_category(category_name: str) -> list[str]:
    """
    Returns a list of item IDs belonging to the specified category defined in config.

    Args:
        category_name: The name of the category (must match a key in config's item_categories).

    Returns:
        A list of matching item IDs, or an empty list if category not found or no items match.
    """
    _load_item_data() # Ensure data is loaded

    logging.debug(f"[Category] Expanding '{category_name}'. Item map size: {len(ITEM_ID_TO_NAME)}.")
    if not ITEM_ID_TO_NAME:
        logging.error(f"[Category] Cannot expand '{category_name}', ITEM_ID_TO_NAME is empty.")
        return []
    else:
        # --- Add this debugging block ---
        keys_sample = list(ITEM_ID_TO_NAME.keys())[:5]
        names_sample = [ITEM_ID_TO_NAME[k] for k in keys_sample]
        logging.debug(f"[Category] Item map seems populated. Sample keys: {keys_sample}")
        logging.debug(f"[Category] Corresponding sample names: {names_sample}")
        # --- End debugging block ---


    category_rule = ITEM_CATEGORIES.get(category_name)
    if not category_rule:
        logging.warning(f"Category '{category_name}' not found in configuration.")
        return []

    rule_type = category_rule.get('type')
    rule_value = category_rule.get('value')
    if not rule_type or rule_value is None: # Allow empty string for value? Check rules.
        logging.warning(f"Invalid rule definition for category '{category_name}': {category_rule}")
        return []

    matching_ids = []
    try:
        if rule_type == 'list':
            # Value should be a list of IDs
            if isinstance(rule_value, list):
                # Validate that these IDs actually exist in our mapping
                matching_ids = [item_id for item_id in rule_value if item_id in ITEM_ID_TO_NAME]
                if len(matching_ids) != len(rule_value):
                    logging.warning(f"Category '{category_name}': Some listed IDs not found ({len(rule_value) - len(matching_ids)} missing).")
            else:
                logging.warning(f"Category '{category_name}' type 'list' requires a list value.")
        elif rule_type == 'regex':
             # Value should be a regex pattern string
             if isinstance(rule_value, str):
                 pattern = re.compile(rule_value)
                 matching_ids = [item_id for item_id in ITEM_ID_TO_NAME if pattern.match(item_id)]
             else:
                 logging.warning(f"Category '{category_name}' type 'regex' requires a string pattern value.")
        elif rule_type == 'name_contains':
            # Value should be a substring to find in item names (case-insensitive)
            if isinstance(rule_value, str):
                 search_term_lower = rule_value.lower()
                 matching_ids = [item_id for item_id, item_name in ITEM_ID_TO_NAME.items() if search_term_lower in item_name.lower()]
            else:
                 logging.warning(f"Category '{category_name}' type 'name_contains' requires a string value.")
        # Add other rule types like 'prefix' if needed
        # elif rule_type == 'prefix':
        #     if isinstance(rule_value, str):
        #         matching_ids = [item_id for item_id in ITEM_ID_TO_NAME if item_id.startswith(rule_value)]
        #     else:
        #          logging.warning(f"Category '{category_name}' type 'prefix' requires a string value.")
        else:
            logging.warning(f"Unsupported category rule type '{rule_type}' for category '{category_name}'.")

    except re.error as e:
         logging.error(f"Invalid regex pattern '{rule_value}' for category '{category_name}': {e}")
         return []
    except Exception as e:
        logging.error(f"Error processing category '{category_name}': {e}", exc_info=True)
        return []

    if not matching_ids:
        logging.info(f"[Category] No items found for '{category_name}'.")
    else:
        logging.debug(f"[Category] '{category_name}' expanded to {len(matching_ids)} items.")

    return matching_ids


# --- Initialization / Example ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s [%(module)s] %(message)s')
    print("--- Item Mapping & Category Test ---")
    _load_item_data()

    if not ITEM_ID_TO_NAME:
        print("Item data loading failed.")
    else:
        print(f"Loaded {len(ITEM_ID_TO_NAME)} items.")
        print(f"Loaded {len(ITEM_CATEGORIES)} categories.")

        # Test category expansion
        # categories_to_test = ["T4 Resources", "All Bags", "Bags T4-T6", "NonExistentCategory"]
        categories_to_test = list(ITEM_CATEGORIES.keys())[:3] # Test first 3 defined categories
        categories_to_test.append("NonExistentCategory")

        for cat in categories_to_test:
            print(f"\nTesting Category: '{cat}'")
            ids = get_item_ids_by_category(cat)
            print(f"  Found {len(ids)} items.")
            if ids:
                print(f"  Examples: {ids[:5]}")

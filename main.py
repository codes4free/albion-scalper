import logging
import argparse # Import argparse
import yaml # Needed for dumping config if debugging
from utils.config_loader import load_config, get_config
from analyzer.scalper import find_potential_scalps
from utils.item_mapping import get_item_ids_by_category, get_all_item_ids, get_item_name, _load_item_data

# --- Argument Parsing ---
def parse_arguments():
    parser = argparse.ArgumentParser(description="Albion Online Market Scalp Analyzer")

    # Load config temporarily to get defaults for help messages
    try:
        temp_config = get_config()
        analysis_defaults = temp_config.get('analysis', {})
        locations_defaults = temp_config.get('locations', {})
        logging_defaults = temp_config.get('logging', {})
        item_categories_defaults = temp_config.get('item_categories', {})
    except Exception: # Handle case where config doesn't exist yet
        analysis_defaults = {}
        locations_defaults = {}
        logging_defaults = {}
        item_categories_defaults = {}

    # --- Analysis Arguments ---
    analysis_group = parser.add_argument_group('Analysis Options')
    analysis_group.add_argument(
        "--items",
        type=str,
        help="Comma-separated list of specific item IDs to analyze (e.g., T4_WOOD,T5_BAG)."
    )
    analysis_group.add_argument(
        "--categories",
        type=str,
        help="Comma-separated list of item categories defined in config to analyze (e.g., \"T4 Resources\",\"All Bags\")."
             f" Available: {list(item_categories_defaults.keys())}"
    )
    analysis_group.add_argument(
        "--locations",
        type=str,
        help="Comma-separated list of locations to analyze (e.g., Lymhurst,Caerleon,\"Black Market\")."
             f" Overrides config default ({len(locations_defaults.get('all_cities', []))} locations)."
    )
    analysis_group.add_argument(
        "--quality",
        type=int,
        default=analysis_defaults.get('default_quality', 1),
        choices=[1, 2, 3, 4, 5],
        help="Item quality level (1-5)."
             f" Overrides config default ({analysis_defaults.get('default_quality', 1)})."
    )
    analysis_group.add_argument(
        "--min-profit",
        type=int,
        default=analysis_defaults.get('min_net_profit', 0),
        help="Minimum net profit in silver required to show a scalp."
             f" Overrides config default ({analysis_defaults.get('min_net_profit', 0):,})."
    )
    analysis_group.add_argument(
        "--limit",
        type=int,
        default=analysis_defaults.get('result_limit', 20),
        help="Maximum number of results to display."
             f" Overrides config default ({analysis_defaults.get('result_limit', 20)})."
    )
    analysis_group.add_argument(
        "--premium",
        action="store_true", # Sets to True if flag is present
        default=analysis_defaults.get('use_premium_tax_rate', False),
        help="Calculate taxes assuming player has Premium status."
             f" Overrides config default ({analysis_defaults.get('use_premium_tax_rate', False)})."
    )
    analysis_group.add_argument(
        "--min-volume",
        type=int,
        default=None,
        help="Minimum average daily volume (in sell location) required to show a scalp."
             f" Overrides config default ({analysis_defaults.get('min_avg_daily_volume', 'N/A')}). Set to 0 to disable."
    )
    analysis_group.add_argument(
        "--no-history",
        action="store_true",
        default=False,
        help="Disable fetching history data and volume filtering, even if enabled in config."
    )

    # --- Utility Arguments ---
    utility_group = parser.add_argument_group('Utility Options')
    utility_group.add_argument(
        "--list-categories",
        action="store_true",
        help="List all available item categories defined in config and exit."
    )
    utility_group.add_argument(
        "--test-category",
        type=str,
        metavar="CATEGORY_NAME",
        help="Show the item IDs expanded by a specific category name and exit."
    )

    # --- General Arguments ---
    parser.add_argument(
        "--log-level",
        type=str,
        default=logging_defaults.get('level', 'INFO').upper(),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help="Set the logging output level."
             f" Overrides config default ({logging_defaults.get('level', 'INFO').upper()})."
    )

    # Parse arguments, potentially overriding defaults loaded above
    args = parser.parse_args()

    # Post-process comma-separated arguments
    if args.items:
        args.items = [item.strip() for item in args.items.split(',')]
    if args.categories:
        # Handle potential quotes around category names if needed, similar to locations
        args.categories = [cat.strip().strip('"') for cat in args.categories.split(',')]
    if args.locations:
        args.locations = [loc.strip().strip('"') for loc in args.locations.split(',')]

    return args


# --- Main Execution ---

# Load configuration first
try:
    config = load_config()
    ANALYSIS_CONFIG = config.get('analysis', {})
    LOCATIONS_CONFIG = config.get('locations', {})
    LOGGING_CONFIG = config.get('logging', {})
    ITEM_CATEGORIES_CONFIG = config.get('item_categories', {})
except (FileNotFoundError, ValueError) as e:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [CONFIG_ERROR] %(message)s')
    logging.error(f"Failed to load configuration: {e}. Using defaults.")
    ANALYSIS_CONFIG = {}
    LOCATIONS_CONFIG = {}
    LOGGING_CONFIG = {}
    ITEM_CATEGORIES_CONFIG = {}


# Parse command-line arguments (potentially overriding config defaults)
args = parse_arguments()

# Setup logging - Use CLI arg > config > default
log_level_str = args.log_level if args.log_level else LOGGING_CONFIG.get('level', 'INFO').upper()
log_format = LOGGING_CONFIG.get('format', '%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s')
logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO), format=log_format)


def display_results(scalps: list[dict], limit: int = 20):
    """Prints the found scalp opportunities to the console."""
    if not scalps:
        print("\nNo profitable scalps found matching the criteria.")
        return

    print(f"\n--- Top {min(limit, len(scalps))} Potential Scalps Found (After Tax & Volume Filter) ---")
    for i, scalp in enumerate(scalps[:limit]):
        buy_price_str = f"{scalp['buy_price']:,}"
        sell_price_str = f"{scalp['sell_price']:,}"
        tax_str = f"{scalp['estimated_tax']:,}"
        net_profit_str = f"{scalp['potential_net_profit']:,}"
        margin_str = f"{scalp['profit_margin_percent']:.2f}%"
        volume_str = f"{scalp.get('avg_daily_volume'):,}" if scalp.get('avg_daily_volume') is not None else "N/A"

        print(f"{i+1}. {scalp['item_name']} (Q{scalp['quality']})")
        print(f"   Buy : {scalp['buy_location']:<15} @ {buy_price_str:>12} silver")
        print(f"   Sell: {scalp['sell_location']:<15} @ {sell_price_str:>12} silver")
        print(f"   Tax : {'':<15} @ {tax_str:>12} silver (estimated)")
        print(f"   Vol : {f'(Sell Loc Avg Daily):':<20} {volume_str:>9}")
        print(f"   ---> Net Profit: {net_profit_str:>9} silver ({margin_str})")
        print("-" * 50) # Adjusted separator width

    if len(scalps) > limit:
        print(f"... and {len(scalps) - limit} more.")

def run_analysis(args): # Pass parsed args
    """
    Uses parameters derived from config and overridden by CLI args.
    """
    logging.info("Starting Albion Trade Analysis...")

    # --- Explicitly Trigger Item Data Loading ---
    logging.info("Ensuring item data is loaded...")
    # Call a function that guarantees _load_item_data runs
    _ = get_all_item_ids() # Getting all IDs will trigger the load if needed
    # OR explicitly call: _load_item_data()
    logging.info("Item data load process triggered.")
    # --- End Trigger ---

    # --- Determine Effective Parameters (CLI > Config > Default) ---
    locations_to_analyze = args.locations if args.locations is not None else LOCATIONS_CONFIG.get('all_cities', [])
    quality_level = args.quality
    min_profit_threshold = args.min_profit
    display_limit = args.limit
    use_premium_tax = args.premium # Use the boolean value from args

    # Determine volume threshold (CLI > Config > Default=0)
    # If --no-history is set, force threshold to 0 to disable filtering logic
    if args.no_history:
         min_volume_thresh = 0
         logging.info("History fetching and volume filtering disabled via --no-history flag.")
    elif args.min_volume is not None: # User specified via CLI
        min_volume_thresh = args.min_volume
    else: # Use config default
         min_volume_thresh = ANALYSIS_CONFIG.get('min_avg_daily_volume', 0)

    # --- Determine Items to Analyze (CLI > Config > Default) ---
    final_item_ids = set() # Use a set to avoid duplicates

    # 1. Add items from --items argument
    if args.items:
        logging.info(f"Adding {len(args.items)} items from --items argument.")
        final_item_ids.update(args.items)

    # 2. Add items from --categories argument
    if args.categories:
        logging.info(f"Expanding categories from --categories argument: {args.categories}")
        for category_name in args.categories:
            ids_from_category = get_item_ids_by_category(category_name)
            if ids_from_category:
                logging.debug(f"Category '{category_name}' expanded to {len(ids_from_category)} items.")
                final_item_ids.update(ids_from_category)
            else:
                logging.warning(f"Category '{category_name}' yielded no items.")

    # 3. If no items specified via CLI, use defaults from config
    if not final_item_ids:
        logging.info("No items specified via CLI, using defaults from config.")
        default_config_items = ANALYSIS_CONFIG.get('default_items', [])
        default_config_categories = ANALYSIS_CONFIG.get('default_categories', [])

        if default_config_items:
            logging.info(f"Adding {len(default_config_items)} items from config 'default_items'.")
            final_item_ids.update(default_config_items)

        if default_config_categories:
            logging.info(f"Expanding categories from config 'default_categories': {default_config_categories}")
            for category_name in default_config_categories:
                 ids_from_category = get_item_ids_by_category(category_name)
                 if ids_from_category:
                     logging.debug(f"Config category '{category_name}' expanded to {len(ids_from_category)} items.")
                     final_item_ids.update(ids_from_category)
                 else:
                     logging.warning(f"Config category '{category_name}' yielded no items.")

    # Convert set back to list for the API call
    items_to_analyze = sorted(list(final_item_ids)) # Sort for consistency

    # --- Validate Parameters ---
    if not items_to_analyze:
        logging.error("No items selected for analysis (check CLI args and config defaults). Cannot proceed.")
        return
    if not locations_to_analyze:
         logging.error("No locations specified. Cannot perform analysis.")
         return

    # --- Run Analysis ---
    logging.info(f"Analyzing {len(items_to_analyze)} unique items.")
    if len(items_to_analyze) > 5: logging.info(f"   (Examples: {items_to_analyze[:5]}...)")
    else: logging.info(f"   Items: {items_to_analyze}")
    logging.info(f"Across {len(locations_to_analyze)} locations: {locations_to_analyze}")
    logging.info(f"Quality: {quality_level}, Min Profit: {min_profit_threshold:,}, Premium Tax: {use_premium_tax}")
    logging.info(f"Filtering for minimum avg daily volume (sell loc): {min_volume_thresh if min_volume_thresh > 0 else 'Disabled'}")

    potential_scalps = find_potential_scalps(
        item_ids=items_to_analyze,
        locations=locations_to_analyze,
        quality=quality_level,
        min_net_profit=min_profit_threshold,
        use_premium=use_premium_tax,
        min_volume_threshold=min_volume_thresh # Pass the determined threshold
    )

    # --- Display Results ---
    display_results(potential_scalps, limit=display_limit)

    logging.info("Analysis complete.")


# --- New Utility Functions ---
def list_categories():
    """Prints the defined item categories from the config."""
    print("\n--- Available Item Categories ---")
    if not ITEM_CATEGORIES_CONFIG:
        print("No item categories found or loaded from config/settings.yaml.")
        return
    # Print sorted category names
    for category_name in sorted(ITEM_CATEGORIES_CONFIG.keys()):
        print(f"- {category_name}")
    print("\nUse --test-category \"<Category Name>\" to see expanded item IDs.")

def test_category(category_name):
    """Tests a category and prints the resulting item IDs."""
    print(f"\n--- Testing Category Expansion: \"{category_name}\" ---")
    logging.info("Ensuring item data is loaded for category test...")
    _load_item_data() # Make sure item list is loaded

    item_ids = get_item_ids_by_category(category_name)

    if not item_ids:
        print(f"No items found for category \"{category_name}\".")
        print("Reasons could be: category name typo, rule doesn't match any items, or item data failed to load (check logs).")
    else:
        print(f"Category \"{category_name}\" expands to {len(item_ids)} items:")
        # Print ID and Name for clarity
        for item_id in sorted(item_ids):
            item_name = get_item_name(item_id) or "(Name not found)"
            print(f"- {item_id:<25} | {item_name}")


if __name__ == "__main__":
    # Handle utility arguments first
    if args.list_categories:
        list_categories()
    elif args.test_category:
        test_category(args.test_category)
    else:
        # If no utility args, run the main analysis
        run_analysis(args)

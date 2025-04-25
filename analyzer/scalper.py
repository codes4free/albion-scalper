import logging
from collections import defaultdict
from statistics import mean # For averaging volume if needed
from data_fetcher.market_data import get_item_prices, get_item_history
from utils.item_mapping import get_item_name
from utils.config_loader import get_config # Import config loader

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Assume logging is configured by the main script or caller

# --- Load Configuration ---
try:
    config = get_config()
    LOCATIONS_CONFIG = config.get('locations', {})
    TAX_CONFIG = config.get('taxes', {})
    ANALYSIS_CONFIG = config.get('analysis', {})

    ROYAL_CITIES = LOCATIONS_CONFIG.get('royal_cities', [])
    ARTIFACT_CITIES = LOCATIONS_CONFIG.get('artifact_cities', [])
    BLACK_MARKET = LOCATIONS_CONFIG.get('black_market', 'Black Market') # Default fallback
    ALL_CITIES_DEFAULT = LOCATIONS_CONFIG.get('all_cities', ROYAL_CITIES + ARTIFACT_CITIES + [BLACK_MARKET]) # Default fallback

    TAX_RATES = TAX_CONFIG.get('rates', {'royal': 0.03, 'caerleon': 0.06, 'black_market': 0.04}) # Defaults
    PREMIUM_MODIFIER = TAX_CONFIG.get('premium_modifier', 0.5)
    USE_PREMIUM_TAX = ANALYSIS_CONFIG.get('use_premium_tax_rate', False)

    # Get volume analysis settings
    FETCH_HISTORY = ANALYSIS_CONFIG.get('fetch_history', False)
    MIN_AVG_DAILY_VOLUME = ANALYSIS_CONFIG.get('min_avg_daily_volume', 0)

except Exception as e:
    logging.error(f"Failed to load config for analyzer, using defaults. Error: {e}")
    # Define safe defaults if config loading fails catastrophically
    ROYAL_CITIES = ["Lymhurst", "Bridgewatch", "Martlock", "Thetford", "Fort Sterling"]
    ARTIFACT_CITIES = ["Caerleon"]
    BLACK_MARKET = "Black Market"
    ALL_CITIES_DEFAULT = ROYAL_CITIES + ARTIFACT_CITIES + [BLACK_MARKET]
    TAX_RATES = {'royal': 0.03, 'caerleon': 0.06, 'black_market': 0.04}
    PREMIUM_MODIFIER = 0.5
    USE_PREMIUM_TAX = False
    FETCH_HISTORY = False; MIN_AVG_DAILY_VOLUME = 0 # Disable volume filtering on error

def get_tax_rate(location: str, use_premium: bool) -> float:
    """Determines the estimated sales tax rate for a given location from config."""
    base_rate = TAX_RATES.get("royal") # Start with royal as default/fallback

    if location in ROYAL_CITIES:
        base_rate = TAX_RATES.get("royal", 0.03)
    elif location == BLACK_MARKET:
        base_rate = TAX_RATES.get("black_market", 0.04)
    elif location in ARTIFACT_CITIES:
        base_rate = TAX_RATES.get("caerleon", 0.06)
    else:
        logging.warning(f"Unknown location for tax rate: {location}. Defaulting to Royal rate.")

    # Apply premium modifier if configured
    if use_premium:
        return base_rate * PREMIUM_MODIFIER
    else:
        return base_rate

def find_potential_scalps(
    item_ids: list[str],
    locations: list[str] | None = None,
    quality: int = 1,
    min_net_profit: int = 1,
    use_premium: bool = False,
    min_volume_threshold: int | None = None
):
    """
    Analyzes market data, optionally fetching history for volume filtering.

    Args:
        item_ids: A list of item IDs to analyze.
        locations: A list of locations to compare prices across. Defaults to all major cities + Black Market.
        quality: The specific item quality level (1-5) to analyze.
        min_net_profit: The minimum net profit required for a scalp to be included in results.
        use_premium: If True, calculates tax using the premium modifier.
        min_volume_threshold: Overrides the minimum volume from config if provided.

    Returns:
        A list of dictionaries, where each dictionary represents a potential scalp opportunity.
        Returns an empty list if no data is fetched or no opportunities are found.
        Example opportunity dict:
        {
            "item_id": "T4_BAG",
            "item_name": "Adept's Bag",
            "quality": 1,
            "buy_location": "Lymhurst",
            "buy_price": 5000,
            "sell_location": "Black Market",
            "sell_price": 6000,
            "estimated_tax": 240, # sell_price * tax_rate
            "potential_gross_profit": 1000,
            "potential_net_profit": 760, # gross_profit - estimated_tax
            "profit_margin_percent": 15.2 # Based on net profit / buy_price
        }
    """
    analysis_locations = locations if locations is not None else ALL_CITIES_DEFAULT
    volume_filter = min_volume_threshold if min_volume_threshold is not None else MIN_AVG_DAILY_VOLUME
    should_fetch_history = FETCH_HISTORY and volume_filter > 0

    logging.info(f"Finding scalps for {len(item_ids)} items in {analysis_locations} (Q{quality})")
    logging.info(f"Tax: {'Premium' if use_premium else 'Standard'}, Min Profit: {min_net_profit:,}, Min Volume: {volume_filter if should_fetch_history else 'N/A'}")

    # --- Fetch Price Data ---
    price_data = get_item_prices(item_ids, locations=analysis_locations, qualities=[quality])
    if not price_data: logging.warning("[Scalper] No price data received."); return []

    # --- Fetch History Data (Optional) ---
    history_data_map = defaultdict(lambda: defaultdict(int)) # item_id -> location -> avg_volume
    if should_fetch_history:
        logging.info("[Scalper] Fetching history data for volume analysis...")
        history_raw = get_item_history(item_ids, locations=analysis_locations, quality=quality)
        if history_raw:
            logging.info(f"[Scalper] Processing {len(history_raw)} item/location history entries...")
            temp_volume_store = defaultdict(lambda: defaultdict(list)) # item -> loc -> [vol1, vol2,...]
            processed_point_count = 0

            # --- Corrected History Parsing Logic ---
            for item_loc_entry in history_raw: # Iterate through the outer list [{loc, item, data:[...]}, ...]
                item_id = item_loc_entry.get('item_id')
                loc = item_loc_entry.get('location')
                data_points = item_loc_entry.get('data', []) # Get the nested list of data points

                if not item_id or not loc:
                    logging.warning(f"[Scalper|HistoryProc] Skipping entry missing item_id or location: {item_loc_entry}")
                    continue

                if not isinstance(data_points, list):
                     logging.warning(f"[Scalper|HistoryProc] Skipping entry with invalid 'data' field (not a list) for {item_id} at {loc}.")
                     continue

                # Iterate through the actual data points within the nested 'data' list
                for data_point in data_points:
                    volume = data_point.get('item_count', 0)
                    timestamp = data_point.get('timestamp', 'N/A')

                    # Log first few actual data points extracted
                    if processed_point_count < 10:
                         logging.debug(f"[Scalper|HistoryProc] Point - Item: {item_id}, Loc: {loc}, Vol: {volume}, Time: {timestamp}")

                    temp_volume_store[item_id][loc].append(volume)
                    processed_point_count += 1
            # --- End Corrected Logic ---

            logging.info(f"[Scalper] Processed {processed_point_count} total history data points.")
            logging.info(f"[Scalper] Aggregated volume data for {len(temp_volume_store)} item/location pairs.")

            # Calculate average volume
            avg_calc_count = 0
            for item_id, loc_data in temp_volume_store.items():
                for loc, volumes in loc_data.items():
                    if volumes:
                        avg_vol = int(mean(volumes))
                        history_data_map[item_id][loc] = avg_vol
                        if avg_calc_count < 10: logging.debug(f"[Scalper|HistoryAvg] Item: {item_id}, Loc: {loc}, Avg Vol: {avg_vol} from {len(volumes)} points")
                        avg_calc_count += 1
                    else:
                         history_data_map[item_id][loc] = 0
            logging.info(f"[Scalper] Calculated average volumes for {len(history_data_map)} items.")
        else:
            logging.warning("[Scalper] Failed to fetch/process history data, volume filtering skipped.")
            should_fetch_history = False # Disable filter

    # --- Organize Price Data ---
    market_info = defaultdict(dict)
    for item_data in price_data:
        # Make sure city name matches exactly (case-sensitive as per API examples)
        location = item_data.get('city')
        if not location: continue # Skip if no city info

        # Ensure the data is for the correct quality and location
        if item_data.get('quality') == quality and location in analysis_locations:
            item_id = item_data['item_id']
            buy_price = max(0, item_data.get('buy_price_max', 0))
            sell_price = max(0, item_data.get('sell_price_min', 0))

            market_info[item_id][location] = {
                "buy": buy_price,
                "sell": sell_price
            }

    potential_scalps = []

    for item_id, locations_data in market_info.items():
        item_name = get_item_name(item_id) or item_id

        # Make sure buy_loc is one of the locations we intended to analyze
        valid_buy_locations = [loc for loc in locations_data if loc in analysis_locations and loc != BLACK_MARKET]

        for buy_loc in valid_buy_locations:
            buy_price_info = locations_data[buy_loc]
            buy_price = buy_price_info['sell']
            if buy_price <= 0: continue

            valid_sell_locations = [loc for loc in locations_data if loc in analysis_locations and loc != buy_loc]

            for sell_loc in valid_sell_locations:
                sell_price_info = locations_data[sell_loc]
                sell_price = sell_price_info['buy']
                if sell_price <= 0: continue

                # --- Volume Check ---
                if should_fetch_history:
                    avg_volume_sell_loc = history_data_map.get(item_id, {}).get(sell_loc, 0)
                    logging.debug(f"[Scalper|VolumeCheck] Item: {item_id} ({buy_loc}->{sell_loc}), SellLocVol: {avg_volume_sell_loc}, Threshold: {volume_filter}")
                    if avg_volume_sell_loc < volume_filter:
                        logging.debug(f"Skipping {item_id} ({buy_loc}->{sell_loc}): Volume {avg_volume_sell_loc} < {volume_filter}")
                        continue # Skip if volume is too low
                else:
                    avg_volume_sell_loc = None # Indicate volume wasn't checked

                # --- Profit Calculation (same as before) ---
                potential_gross_profit = sell_price - buy_price
                if potential_gross_profit <= 0: continue
                tax_rate = get_tax_rate(sell_loc, use_premium)
                estimated_tax = int(sell_price * tax_rate)
                potential_net_profit = potential_gross_profit - estimated_tax

                if potential_net_profit >= min_net_profit:
                    try:
                        profit_margin = (potential_net_profit / buy_price) * 100
                    except ZeroDivisionError:
                        profit_margin = float('inf') if potential_net_profit > 0 else 0

                    scalp = {
                        "item_id": item_id, "item_name": item_name, "quality": quality,
                        "buy_location": buy_loc, "buy_price": buy_price,
                        "sell_location": sell_loc, "sell_price": sell_price,
                        "estimated_tax": estimated_tax,
                        "potential_gross_profit": potential_gross_profit,
                        "potential_net_profit": potential_net_profit,
                        "profit_margin_percent": round(profit_margin, 2),
                        # Add volume info
                        "avg_daily_volume": avg_volume_sell_loc
                    }
                    potential_scalps.append(scalp)

    potential_scalps.sort(key=lambda x: x['potential_net_profit'], reverse=True)
    logging.info(f"Found {len(potential_scalps)} potential scalp opportunities meeting all criteria.")
    return potential_scalps


# Example usage
if __name__ == "__main__":
    # Setup basic logging for test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        # Load config for example run parameters
        cfg = get_config()
        items_to_analyze = cfg.get('analysis', {}).get('default_items', [])[:5] # Limit items for example
        target_locations = cfg.get('locations', {}).get('all_cities', [])
        quality_level = cfg.get('analysis', {}).get('default_quality', 1)
        min_profit_threshold = cfg.get('analysis', {}).get('min_net_profit', 100)
        use_premium = cfg.get('analysis', {}).get('use_premium_tax_rate', False) # Check if premium is used
        volume_threshold = cfg.get('analysis', {}).get('min_avg_daily_volume', 0) # Check if volume threshold is set

        print(f"\n--- Running Standalone Scalper Example ---")
        print(f"Items: {items_to_analyze}")
        print(f"Locations: {target_locations}")
        print(f"Quality: {quality_level}")
        print(f"Min Net Profit: {min_profit_threshold:,}")
        print(f"Using Premium Tax Rates: {use_premium}")
        print(f"Volume Threshold: {volume_threshold if volume_threshold > 0 else 'N/A'}")
        print("-" * 30)

        scalps = find_potential_scalps(
            item_ids=items_to_analyze,
            locations=target_locations, # Explicitly pass locations
            quality=quality_level,
            min_net_profit=min_profit_threshold,
            use_premium=use_premium,
            min_volume_threshold=volume_threshold
        )

        # Basic printout for example
        if scalps:
            print(f"\nFound {len(scalps)} scalps:")
            for i, scalp in enumerate(scalps[:5]): # Show top 5
                print(f"  {i+1}. {scalp['item_name']} ({scalp['buy_location']} -> {scalp['sell_location']}) "
                      f"Net Profit: {scalp['potential_net_profit']:,}")
        else:
            print("\nNo profitable scalps found.")

    except (FileNotFoundError, ValueError) as e:
        print(f"Failed to load config for example run: {e}")
    except Exception as e:
         print(f"An error occurred during example run: {e}")

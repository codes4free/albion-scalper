import streamlit as st
import pandas as pd
import logging # Import logging
import numpy as np # Needed for styling potential NaNs
from matplotlib.colors import to_rgb, CSS4_COLORS # Import color tools
from passlib.context import CryptContext # Import for password verification
# Removed: from pathlib import Path # No longer needed for logo
import base64 # Keep if needed elsewhere, otherwise remove

# --- Logo Path (as string) ---
LOGO_PATH = "images/albion_logo.png" # <<< Define as a simple string path

# --- Setup Logging Early ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s')

# --- Password Context ---
# Use same context as used for hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Backend Imports ---
try:
    from utils.config_loader import get_config
    from utils.item_mapping import get_item_ids_by_category, get_item_name, _load_item_data
    from analyzer.scalper import find_potential_scalps, ALL_CITIES_DEFAULT # Import default cities list
except ImportError as e:
    logging.error(f"Import Error: {e}. Cannot start app.")
    st.error(f"Import Error: {e}. Cannot start app.")
    st.stop()

# --- Load Config ---
try:
    config = get_config()
    ITEM_CATEGORIES_CONFIG = config.get('item_categories', {})
    ANALYSIS_CONFIG = config.get('analysis', {})
    LOCATIONS_CONFIG = config.get('locations', {})
    # Get default locations from config or fallback
    DEFAULT_LOCATIONS = LOCATIONS_CONFIG.get('all_cities', ALL_CITIES_DEFAULT)
except Exception as e:
    st.error(f"Failed to load config: {e}")
    ITEM_CATEGORIES_CONFIG = {}
    ANALYSIS_CONFIG = {}
    DEFAULT_LOCATIONS = []
    # Consider stopping or using hardcoded defaults
    # st.stop()

# Ensure item data is loaded once on startup for category list/mapping
try:
    _load_item_data()
except Exception as e:
    st.warning(f"Failed to preload item data: {e}. Category expansion might fail.")


# --- City Color & Icon Mapping (Only Table Icons and Table Colors used now) ---
CITY_COLOR_MAP = { # For results table background
    "black market": "#333333", "martlock": "#6A7E9B", "lymhurst": "#5A8B4C",
    "fort sterling": "#F5F5DC", "bridgewatch": "#D28445", "caerleon": "#DC143C",
    "thetford": "#7E5A9B",
}
# Icons for results table cells
TABLE_ICON_MAP = {
    "black market": "⚫", "martlock": "🛡️", "lymhurst": "🌳", "fort sterling": "🔨",
    "bridgewatch": "🔥", "caerleon": "💀", "thetford": "🍇",
}

# Icons for sidebar multiselect list
SIDEBAR_ICON_MAP = {
    "black market": "⚫", "martlock": "🔵", "lymhurst": "🟢", "fort sterling": "⚪",
    "bridgewatch": "🟠", "caerleon": "🔴", "thetford": "🟣",
}

def get_sidebar_icon(city):
    """Returns the thematic emoji for the sidebar multiselect list."""
    return SIDEBAR_ICON_MAP.get(str(city).lower(), "") # Default empty

def get_table_icon(city):
    """Returns the thematic emoji for the results table."""
    return TABLE_ICON_MAP.get(str(city).lower(), "") # Default empty

# --- Styling Functions (Restored/Used for Table) ---
def get_text_color_for_bg(bg_color_hex):
    """Chooses black or white text based on background luminance."""
    try:
        rgb = to_rgb(bg_color_hex)
        luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
        return 'black' if luminance > 0.5 else 'white'
    except ValueError:
        return 'black'

def apply_style_to_icon_cell(cell_value):
    """Applies background and text color based on city name extracted from cell."""
    # Expects format like "🌳 Lymhurst"
    city_name = str(cell_value).split(" ", 1)[-1] # Get text after first space
    city_lower = city_name.lower()
    bg_color = CITY_COLOR_MAP.get(city_lower, None)
    if bg_color:
        text_color = get_text_color_for_bg(bg_color)
        # Apply background, text color, and centering
        return f'background-color: {bg_color}; color: {text_color}; text-align: center;'
    # Apply centering even if no color map found
    return 'text-align: center;'
# --- End Styling Functions ---


# --- Authentication Functions ---
def check_credentials(username, password):
    """Verifies username and password against secrets."""
    try:
        # Access the credentials stored in secrets.toml
        user_credentials = st.secrets["credentials"]
        if username in user_credentials:
            stored_hashed_password = user_credentials[username]
            # Verify the provided password against the stored hash
            return pwd_context.verify(password, stored_hashed_password)
        return False # Username not found
    except Exception as e:
        logging.error(f"Error accessing or verifying credentials: {e}")
        st.error("Authentication error. Check server logs or secrets configuration.")
        return False

def login_form():
    """Displays the login form."""
    st.title("🔒 Albion Scalp Analyzer - Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if check_credentials(username, password):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username # Store username if needed
                st.success("Login successful!")
                st.rerun() # Rerun the script to show the dashboard
            else:
                st.error("Incorrect username or password.")

# --- Main Dashboard Function ---
def display_dashboard():
    """Displays the main application dashboard."""
    # --- Page Config (can set tab title/icon here too) ---
    st.set_page_config(
        page_title="Albion Scalp Analyzer",
        # page_icon=LOGO_PATH, # Optionally set browser tab icon
        layout="wide"
    )

    # --- Sidebar ---
    # Display Logo using simple st.sidebar.image
    try:
        st.sidebar.image(LOGO_PATH, width=200) # Use string path directly
    except Exception as e:
        # Let st.image handle FileNotFoundError implicitly, catch other errors
        st.sidebar.error(f"Error loading logo: Check path/file.")
        logging.error(f"Error loading logo image {LOGO_PATH}: {e}", exc_info=True)

    # Add a divider below the logo
    st.sidebar.divider()

    st.sidebar.header("Analysis Filters")
    # Welcome message and Logout button
    if "username" in st.session_state:
        st.sidebar.success(f"Welcome, {st.session_state['username']}!")
    if st.sidebar.button("Logout"):
        st.session_state["authenticated"] = False
        st.session_state.pop("username", None)
        st.rerun()

    # Category Selection
    available_categories = sorted(list(ITEM_CATEGORIES_CONFIG.keys()))
    selected_categories = st.sidebar.multiselect(
        "Item Categories:",
        options=available_categories,
        default=ANALYSIS_CONFIG.get('default_categories', []) # Use defaults from config
    )

    # Specific Item IDs (Optional)
    item_ids_input = st.sidebar.text_input(
        "Specific Item IDs (comma-separated):",
        help="e.g., T4_BAG,T5_CAPE"
    )

    # --- Modified Location Selection (Plain Text Options) ---
    # Use the plain default locations list directly
    location_options_with_icons = [ f"{get_sidebar_icon(loc)} {loc}" for loc in DEFAULT_LOCATIONS ]
    default_location_selection_with_icons = [ f"{get_sidebar_icon(loc)} {loc}" for loc in DEFAULT_LOCATIONS ]
    selected_locations_with_icons = st.sidebar.multiselect(
        "Locations:",
        options=location_options_with_icons,
        default=default_location_selection_with_icons
    )
    selected_locations = [ loc_with_icon.split(" ", 1)[-1] for loc_with_icon in selected_locations_with_icons ]
    # No need to parse icons from the selection anymore
    # --- End Location Selection Modification ---

    # Quality
    selected_quality = st.sidebar.slider(
        "Item Quality:",
        min_value=1,
        max_value=5,
        value=ANALYSIS_CONFIG.get('default_quality', 1),
        step=1
    )

    # Minimum Profit
    min_profit_input = st.sidebar.number_input(
        "Minimum Net Profit (Silver):",
        min_value=0,
        value=ANALYSIS_CONFIG.get('min_net_profit', 100),
        step=100
    )

    # Minimum Volume
    min_volume_input = st.sidebar.number_input(
        "Minimum Avg Daily Volume (Sell Loc):",
        min_value=0,
        value=ANALYSIS_CONFIG.get('min_avg_daily_volume', 10), # Use a smaller default maybe?
        step=10,
        help="Set to 0 to disable volume filtering."
    )
    # Option to disable history fetch entirely
    disable_history = st.sidebar.checkbox(
        "Disable Volume Check (No History Fetch)",
        value=not ANALYSIS_CONFIG.get('fetch_history', True), # Default based on config 'fetch_history'
        help="Overrides minimum volume setting."
    )

    # Premium Tax
    use_premium = st.sidebar.checkbox(
        "Use Premium Tax Rate",
        value=ANALYSIS_CONFIG.get('use_premium_tax_rate', False)
    )

    # --- Main Area ---
    # Remove columns, place title directly
    st.title("Albion Online Market Scalp Analyzer")

    # Button to trigger analysis
    run_button = st.button("🔍 Find Scalps!")

    # Placeholder for results
    results_area = st.empty()
    results_area.info("Configure filters in the sidebar and click 'Find Scalps!'")

    if run_button:
        results_area.info("⏳ Running analysis... Fetching data...")
        logging.info("Analysis triggered from dashboard.")

        # --- Determine Items ---
        final_item_ids = set()
        if item_ids_input:
            ids_list = [item.strip() for item in item_ids_input.split(',')]
            logging.info(f"Adding {len(ids_list)} items from text input.")
            final_item_ids.update(ids_list)

        if selected_categories:
            logging.info(f"Expanding categories: {selected_categories}")
            for category_name in selected_categories:
                ids_from_category = get_item_ids_by_category(category_name)
                if ids_from_category:
                    logging.debug(f"Category '{category_name}' expanded to {len(ids_from_category)} items.")
                    final_item_ids.update(ids_from_category)
                else:
                    logging.warning(f"Category '{category_name}' yielded no items.")

        items_to_analyze = sorted(list(final_item_ids))

        if not items_to_analyze:
            results_area.error("No items selected. Choose categories or enter specific item IDs.")
            return

        if not selected_locations:
            results_area.error("No locations selected.")
            return

        # --- Determine Volume Threshold ---
        effective_min_volume = 0
        if not disable_history:
            effective_min_volume = min_volume_input
        else:
             logging.info("Volume checking disabled by checkbox.")

        # --- Call Backend ---
        try:
            logging.info(f"Calling find_potential_scalps with {len(items_to_analyze)} items, {len(selected_locations)} locations...")
            potential_scalps = find_potential_scalps(
                item_ids=items_to_analyze,
                locations=selected_locations,
                quality=selected_quality,
                min_net_profit=min_profit_input,
                use_premium=use_premium,
                min_volume_threshold=effective_min_volume # Pass calculated threshold
            )
            logging.info(f"Analysis returned {len(potential_scalps)} potential scalps.")

            # --- Display Results ---
            if not potential_scalps:
                results_area.warning("No profitable scalps found matching the criteria.")
            else:
                # Convert results to Pandas DataFrame for better display
                df = pd.DataFrame(potential_scalps)

                # --- Sort by Profit Margin Descending ---
                # Ensure the column exists before sorting
                if 'profit_margin_percent' in df.columns:
                     # Convert to numeric, coercing errors to NaN for safe sorting
                     df['profit_margin_percent_numeric'] = pd.to_numeric(df['profit_margin_percent'], errors='coerce')
                     df = df.sort_values(by='profit_margin_percent_numeric', ascending=False, na_position='last')
                     df = df.drop(columns=['profit_margin_percent_numeric']) # Drop helper column
                     logging.debug("Sorted results by profit margin descending.")
                else:
                     logging.warning("Column 'profit_margin_percent' not found for sorting.")
                # --- End Sorting ---

                # Select and reorder columns for display
                display_columns = [
                    'item_name', 'quality',
                    'buy_location', 'buy_price',
                    'sell_location', 'sell_price',
                    'estimated_tax', 'potential_net_profit', 'profit_margin_percent',
                    'avg_daily_volume'
                ]
                # Ensure all columns exist, add missing ones with None if necessary (like avg_daily_volume if history was off)
                for col in display_columns:
                     if col not in df.columns:
                         df[col] = None

                # Ensure margin is numeric *before* renaming/styling
                df['profit_margin_percent'] = pd.to_numeric(df['profit_margin_percent'], errors='coerce')

                df_display = df[display_columns].copy() # Use copy to avoid SettingWithCopyWarning

                # --- Create Icon+Name Columns ---
                df_display['Buy Loc Display'] = df_display['buy_location'].apply(lambda x: f"{get_table_icon(x)} {x}")
                df_display['Sell Loc Display'] = df_display['sell_location'].apply(lambda x: f"{get_table_icon(x)} {x}")
                # --- End Icon Prepending ---

                # --- Define FINAL Column Names and Order ---
                column_rename_map = {
                    'item_name': 'Item', 'quality': 'Q',
                    'Buy Loc Display': 'Buy Loc', # Map new col to final name
                    'Sell Loc Display': 'Sell Loc',# Map new col to final name
                    'buy_price': 'Buy Price', 'sell_price': 'Sell Price',
                    'estimated_tax': 'Tax (Est)', 'potential_net_profit': 'Net Profit (Est)',
                    'profit_margin_percent': 'Margin %',
                    'avg_daily_volume': 'Avg Daily Vol (Sell)'
                }
                final_display_order = [ # Order for the table
                     'Item', 'Q', 'Buy Loc', 'Buy Price', 'Sell Loc', 'Sell Price',
                     'Tax (Est)', 'Net Profit (Est)', 'Margin %', 'Avg Daily Vol (Sell)'
                ]

                df_display = df_display.rename(columns=column_rename_map)[final_display_order] # Rename and select order

                format_dict = { # Format dict (uses final names)
                    'Buy Price': "{:,.0f}", 'Sell Price': "{:,.0f}", 'Tax (Est)': "{:,.0f}",
                    'Net Profit (Est)': "{:,.0f}", 'Margin %': "{:.2f}%", 'Avg Daily Vol (Sell)': "{:,.0f}"
                }

                # --- Apply Styling (Re-added city background mapping) ---
                styled_df = df_display.style \
                    .map(apply_style_to_icon_cell, subset=['Buy Loc', 'Sell Loc']) \
                    .background_gradient(cmap='YlGn', subset=['Margin %'], vmin=0) \
                    .set_properties(**{'text-align': 'center'}) \
                    .format(format_dict, na_rep="N/A")

                # Display using st.dataframe
                results_area.success(f"Found {len(potential_scalps)} potential scalps (sorted by Margin %):")
                st.dataframe(styled_df, use_container_width=True, hide_index=True) # Added hide_index

                # Alternative: Static table
                # st.table(df_display.head(20)) # Show top 20 in static table

        except Exception as e:
            logging.error(f"An error occurred during analysis: {e}", exc_info=True)
            results_area.error(f"An error occurred: {e}") 

# --- Main App Logic ---

# Load Config and Item data once (outside main control flow if possible)
try:
    config = get_config(); ITEM_CATEGORIES_CONFIG = config.get('item_categories', {}); ANALYSIS_CONFIG = config.get('analysis', {}); LOCATIONS_CONFIG = config.get('locations', {}); DEFAULT_LOCATIONS = LOCATIONS_CONFIG.get('all_cities', ALL_CITIES_DEFAULT)
except Exception as e: st.error(f"Critical Error: Failed to load config: {e}"); st.stop()
try: _load_item_data()
except Exception as e: st.warning(f"Warning: Failed to preload item data: {e}")

# Initialize session state for authentication
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Check authentication status and display appropriate view
if st.session_state.get("authenticated", False):
    display_dashboard()
else:
    login_form() 
import streamlit as st
st.set_page_config(page_title="Albion Scalper", page_icon=":game_die:", layout="wide", initial_sidebar_state="expanded")

import pandas as pd
import logging # Import logging
import numpy as np # Needed for styling potential NaNs
from matplotlib.colors import to_rgb, CSS4_COLORS # Import color tools
from passlib.context import CryptContext # Import for password verification
# Removed: from pathlib import Path # No longer needed for logo
import base64 # Keep if needed elsewhere, otherwise remove
from datetime import datetime
from utils.auth import (
    send_verification_email,
    create_verification_token,
    verify_token,
    validate_email_address,
    hash_password,
    verify_password,
    pending_registrations
)

# --- Logo Path (as string) ---
LOGO_PATH = "images/albion_logo_new.png"

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
    return SIDEBAR_ICON_MAP.get(str(city).lower(), "⬜") # Default to white square if not found

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
    """Applies text color based on city name extracted from cell."""
    # Expects format like "🌳 Lymhurst"
    city_name = str(cell_value).split(" ", 1)[-1] # Get text after first space
    city_lower = city_name.lower()
    # Only apply centering, no background color
    return 'text-align: center;'
# --- End Styling Functions ---


# --- Authentication Functions ---
def load_user_credentials():
    import json
    # Start with credentials from st.secrets, if available
    credentials = dict(st.secrets.get("credentials", {}))
    try:
        with open("user_credentials.json", "r") as f:
            file_creds = json.load(f)
        credentials.update(file_creds)
        logging.debug(f"Merged credentials: loaded {len(file_creds)} additional users from file.")
    except Exception as e:
        logging.debug(f"No additional user credentials found: {e}")
    logging.debug(f"Total merged credentials count: {len(credentials)}")
    return credentials

def check_credentials(username, password):
    """Verifies username and password against secrets."""
    try:
        # Load merged credentials from st.secrets and user_credentials.json
        user_credentials = load_user_credentials()

        if username not in user_credentials:
            logging.debug(f"Authentication attempt for username '{username}' failed: username not found.")
            return False

        stored_hashed_password = user_credentials[username]
        logging.debug(f"Retrieved hashed password for '{username}' starts with: {stored_hashed_password[:7]}")
        match = pwd_context.verify(password, stored_hashed_password)

        if match:
            logging.debug(f"Authentication attempt for username '{username}' succeeded.")
        else:
            logging.debug(f"Authentication attempt for username '{username}' failed: password mismatch.")

        return match
    except Exception as e:
        logging.error(f"Error accessing or verifying credentials for '{username}': {e}")
        st.error("Authentication error. Check server logs or secrets configuration.")
        return False

def register_form():
    """Displays the registration form."""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("📝 Register New Account")
        with st.form("register_form"):
            email = st.text_input("Email")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Register")

            if submitted:
                # Validate inputs
                if not validate_email_address(email):
                    st.error("Please enter a valid email address.")
                    return
                
                if not username:
                    st.error("Please enter a username.")
                    return
                
                if not password:
                    st.error("Please enter a password.")
                    return
                
                if password != confirm_password:
                    st.error("Passwords do not match.")
                    return
                
                # Check if username already exists
                if username in st.secrets["credentials"]:
                    st.error("Username already exists.")
                    return
                
                # Create verification token and store registration data
                verification_token = create_verification_token(email)
                pending_registrations[verification_token] = {
                    "email": email,
                    "username": username,
                    "password": hash_password(password),
                    "timestamp": datetime.now()
                }
                
                # Send verification email
                if send_verification_email(email, verification_token):
                    st.success("Registration successful! Please check your email to verify your account.")
                else:
                    st.error("Failed to send verification email. Please try again later.")

def update_user_credentials(username, password):
    import json
    credentials_file = "user_credentials.json"
    try:
        with open(credentials_file, "r") as f:
            credentials = json.load(f)
    except FileNotFoundError:
        credentials = {}
    credentials[username] = password
    with open(credentials_file, "w") as f:
        json.dump(credentials, f)

def verify_email_page():
    """Handles email verification."""
    token = st.query_params.get("token")
    if not token:
        st.error("No verification token provided.")
        return
    
    email = verify_token(token)
    if not email:
        st.error("Invalid or expired verification token.")
        return
    
    registration_data = pending_registrations.get(token)
    if not registration_data:
        st.warning("Registration data not found. This may indicate that your email has already been verified or the link has expired. Please log in or request a new verification email.")
        st.markdown("[Go to Login](./)", unsafe_allow_html=True)
        return
    
    # Add user to credentials
    update_user_credentials(registration_data["username"], registration_data["password"])
    
    # Remove from pending registrations
    del pending_registrations[token]
    
    st.success("Email verified successfully! You can now log in.")
    st.markdown("[Go to Login](./)", unsafe_allow_html=True)

def login_form():
    """Displays the login form."""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("🔒 Albion Scalp Analyzer - Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                if check_credentials(username, password):
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = username
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
        
        # Add register button
        st.markdown("---")
        st.markdown("Don't have an account?")
        if st.button("Register"):
            st.session_state["show_register"] = True
            st.rerun()

# --- Main Dashboard Function ---
def display_dashboard():
    """Displays the main application dashboard."""
    # Add custom CSS for responsiveness
    st.markdown("""
        <style>
        /* Logo styling */
        div[data-testid="stImage"] img {
            background-color: black !important;
            padding: 1rem !important;
            border-radius: 10px !important;
        }
        
        /* Main container responsiveness */
        .main .block-container {
            padding-top: 1rem;
            padding-right: 1rem;
            padding-left: 1rem;
            padding-bottom: 1rem;
        }
        
        /* Sidebar responsiveness */
        .css-1d391kg {
            padding-top: 1rem;
            padding-right: 1rem;
            padding-left: 1rem;
            padding-bottom: 1rem;
        }
        
        /* Make text and inputs more responsive */
        @media (max-width: 768px) {
            .stButton > button {
                width: 100%;
            }
            
            div[data-testid="stForm"] {
                padding: 0.5rem;
            }
            
            div[data-baseweb="select"] {
                min-width: unset !important;
            }
        }
        
        /* Responsive table */
        div[data-testid="stDataFrame"] {
            width: 100% !important;
            max-width: 100% !important;
        }

        /* Enhanced header styling */
        div[data-testid="stDataFrame"] th,
        .dvn-scroller th {
            font-size: 0.85rem !important;
            padding: 0.15rem 0.25rem !important;
            white-space: nowrap !important;
            text-align: center !important;
            vertical-align: middle !important;
            font-weight: 900 !important;
            width: max-content !important;
            max-width: max-content !important;
            height: 24px !important;
            line-height: 1 !important;
            background-color: #f0f2f6 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.02em !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }

        /* Cell content centering */
        div[data-testid="stDataFrame"] td,
        .dvn-scroller td {
            font-size: 0.85rem !important;
            padding: 0.15rem 0.25rem !important;
            white-space: nowrap !important;
            text-align: center !important;
            vertical-align: middle !important;
            width: max-content !important;
            max-width: max-content !important;
            height: 22px !important;
            line-height: 1 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }

        /* Additional centering for cell content */
        .dvn-scroller .cell-content,
        div[data-testid="stDataFrame"] .cell-content {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
            height: 100% !important;
        }

        /* Make sure the scroller doesn't affect content alignment */
        .dvn-scroller {
            overflow: visible !important;
        }

        .dvn-scroll-inner {
            overflow: visible !important;
        }

        /* Bold first 3 rows */
        div[data-testid="stDataFrame"] tr:nth-child(-n+3) td,
        .dvn-scroller tr:nth-child(-n+3) td {
            font-weight: 700 !important;
        }

        /* Bold first 3 columns */
        div[data-testid="stDataFrame"] td:nth-child(-n+3),
        .dvn-scroller td:nth-child(-n+3) {
            font-weight: 700 !important;
        }

        /* Make table flow naturally */
        div[data-testid="stDataFrame"] table,
        .dvn-scroller table {
            width: max-content !important;
            margin: 0 auto !important;
            border-collapse: collapse !important;
            border-spacing: 0 !important;
            table-layout: auto !important;
        }

        /* Remove height constraints */
        div[data-testid="stDataFrame"] div[data-testid="StyledFullScreenFrame"],
        .dvn-scroller div[data-testid="StyledFullScreenFrame"] {
            max-height: none !important;
            height: auto !important;
            overflow: visible !important;
        }

        /* Adjust column widths to content */
        div[data-testid="stDataFrame"] td, 
        div[data-testid="stDataFrame"] th,
        .dvn-scroller td,
        .dvn-scroller th {
            border: 1px solid #e6e6e6 !important;
            width: max-content !important;
            padding-left: 0.25rem !important;
            padding-right: 0.25rem !important;
            box-sizing: border-box !important;
        }

        /* Remove any scroll containers */
        div[data-testid="stDataFrame"] div,
        .dvn-scroller div {
            overflow: visible !important;
        }

        /* Title alignment */
        h1 {
            text-align: right !important;
        }
        
        /* Override for all tag-like elements */
        [data-testid="stMultiSelect"] span[data-baseweb="tag"],
        div[role="listbox"] span[data-baseweb="tag"],
        div[data-baseweb="select"] span[data-baseweb="tag"] {
            background-color: #808080 !important;
            border-color: #808080 !important;
        }
        
        /* Style for the text and X button */
        [data-testid="stMultiSelect"] span[data-baseweb="tag"] *,
        div[role="listbox"] span[data-baseweb="tag"] *,
        div[data-baseweb="select"] span[data-baseweb="tag"] * {
            color: white !important;
        }

        /* Additional override for any remaining red elements */
        div[class*="stMultiSelect"] span[class*="css"],
        div[class*="stMultiSelect"] div[class*="css"] {
            background-color: #808080 !important;
            border-color: #808080 !important;
            color: white !important;
        }

        /* Responsive font sizes */
        @media (max-width: 768px) {
            h1 {
                font-size: 1.5rem !important;
            }
            h2 {
                font-size: 1.3rem !important;
            }
            p, div {
                font-size: 0.9rem !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)

    # --- Sidebar ---
    # Display Logo using simple st.sidebar.image with responsive width
    try:
        st.sidebar.image(LOGO_PATH, use_container_width=True)
    except Exception as e:
        st.sidebar.error(f"Error loading logo: Check path/file.")
        logging.error(f"Error loading logo image {LOGO_PATH}: {e}", exc_info=True)

    # Add a divider below the logo
    st.sidebar.divider()

    st.sidebar.header("Analysis Filters")
    # Welcome message and Logout button in a more compact layout
    if "username" in st.session_state:
        col1, col2 = st.sidebar.columns([2, 1])
        with col1:
            st.success(f"Welcome, {st.session_state['username']}!")
        with col2:
            if st.button("Logout", use_container_width=True):
                st.session_state["authenticated"] = False
                st.session_state.pop("username", None)
                st.rerun()

    # Category Selection with responsive width
    available_categories = sorted(list(ITEM_CATEGORIES_CONFIG.keys()))
    selected_categories = st.sidebar.multiselect(
        "Item Categories:",
        options=available_categories,
        default=[],
        key="categories_select"
    )
    st.sidebar.markdown("**Tier Filter**")
    tier3 = st.sidebar.checkbox("Tier 3", key="tier3", value=False)
    tier4 = st.sidebar.checkbox("Tier 4", key="tier4", value=False)
    tier5 = st.sidebar.checkbox("Tier 5", key="tier5", value=False)
    tier6 = st.sidebar.checkbox("Tier 6", key="tier6", value=False)
    tier7 = st.sidebar.checkbox("Tier 7", key="tier7", value=False)
    tier8 = st.sidebar.checkbox("Tier 8", key="tier8", value=False)

    # Specific Item IDs with responsive container
    with st.sidebar.container():
        item_ids_input = st.text_input(
            "Specific Item IDs (comma-separated):",
            help="e.g., T4_BAG,T5_CAPE",
            key="item_ids_input"
        )

    # Location Selection with responsive layout
    location_options_with_icons = [f"{get_sidebar_icon(loc)} {loc}" for loc in DEFAULT_LOCATIONS]
    default_location_selection_with_icons = [f"{get_sidebar_icon(loc)} {loc}" for loc in DEFAULT_LOCATIONS]
    selected_locations_with_icons = st.sidebar.multiselect(
        "Locations:",
        options=location_options_with_icons,
        default=default_location_selection_with_icons,
        key="locations_select"
    )
    selected_locations = [loc_with_icon.split(" ", 1)[-1] for loc_with_icon in selected_locations_with_icons]

    # Quality Selection with responsive layout
    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        analyze_all_qualities = st.checkbox(
            "Analyze All Qualities",
            value=False,
            help="Check this to ignore the quality slider and analyze qualities 1-5."
        )
    
    selected_quality = st.sidebar.slider(
        "Item Quality:",
        min_value=1,
        max_value=5,
        value=ANALYSIS_CONFIG.get('default_quality', 1),
        step=1,
        disabled=analyze_all_qualities
    )

    # Profit and Volume inputs in responsive columns
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_profit_input = st.number_input(
            "Min Profit %:",
            min_value=0,
            value=100,
            step=1
        )
    with col2:
        min_volume_input = st.number_input(
            "Min Daily Volume:",
            min_value=0,
            value=100,
            step=10
        )

    # Checkboxes in responsive layout
    col1, col2 = st.sidebar.columns(2)
    with col1:
        disable_history = st.checkbox(
            "Disable Volume",
            value=not ANALYSIS_CONFIG.get('fetch_history', True),
            help="No History Fetch"
        )
    with col2:
        use_premium = st.checkbox(
            "Premium Tax",
            value=ANALYSIS_CONFIG.get('use_premium_tax_rate', False)
        )

    # --- Main Area ---
    # Title and run button in responsive layout
    col1, col2 = st.columns([1, 4])
    with col1:
        run_button = st.button("🔍 Find Scalps!", use_container_width=True)

    # Placeholder for results with responsive container
    results_area = st.empty()
    with results_area.container():
        st.info("Configure filters in the sidebar and click 'Find Scalps!'")

    if run_button:
        with results_area.container():
            st.info("⏳ Running analysis... Fetching data...")
            
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
        # --- Tier Filter ---
        selected_tiers = []
        if st.session_state.get("tier3", False):
            selected_tiers.append("T3_")
        if st.session_state.get("tier4", False):
            selected_tiers.append("T4_")
        if st.session_state.get("tier5", False):
            selected_tiers.append("T5_")
        if st.session_state.get("tier6", False):
            selected_tiers.append("T6_")
        if st.session_state.get("tier7", False):
            selected_tiers.append("T7_")
        if st.session_state.get("tier8", False):
            selected_tiers.append("T8_")
        if selected_tiers:
            final_item_ids = {item_id for item_id in final_item_ids if any(item_id.startswith(tier) for tier in selected_tiers)}

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

        # --- Determine Quality for Backend ---
        quality_to_analyze = None if analyze_all_qualities else selected_quality # Use None for all qualities
        if analyze_all_qualities:
            logging.info("Analysis requested for ALL qualities (1-5).")
        else:
            logging.info(f"Analysis requested for quality: {quality_to_analyze}")

        # --- Call Backend ---
        try:
            logging.info(f"Calling find_potential_scalps with {len(items_to_analyze)} items, {len(selected_locations)} locations...")
            potential_scalps = find_potential_scalps(
                item_ids=items_to_analyze,
                locations=selected_locations,
                quality=quality_to_analyze, # Pass the determined quality value
                min_margin_percent=min_profit_input,
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

                # --- Sort by Opportunity Score (Margin × Volume) ---
                if 'opportunity_score' in df.columns:
                    df = df.sort_values(by='opportunity_score', ascending=False, na_position='last')
                    logging.debug("Sorted results by opportunity score (margin × volume).")
                else:
                    logging.warning("Column 'opportunity_score' not found for sorting.")

                # Select and reorder columns for display
                display_columns = [
                    'item_name', 'quality',
                    'buy_location', 'buy_price',
                    'sell_location', 'sell_price',
                    'estimated_tax', 'potential_net_profit', 'profit_margin_percent',
                    'avg_daily_volume'
                ]

                # Ensure all columns exist, add missing ones with None if necessary
                for col in display_columns:
                    if col not in df.columns:
                        df[col] = None

                # Ensure margin is numeric *before* renaming/styling
                df['profit_margin_percent'] = pd.to_numeric(df['profit_margin_percent'], errors='coerce')

                # Calculate opportunity score for display
                df['opportunity_score'] = df['potential_net_profit'] * df['avg_daily_volume']

                # Sort by opportunity score before creating display dataframe
                df = df.sort_values(by='opportunity_score', ascending=False, na_position='last')

                df_display = df[display_columns + ['opportunity_score']].copy()

                # --- Create Icon+Name Columns ---
                df_display['Buy Loc Display'] = df_display['buy_location'].apply(lambda x: f"{get_table_icon(x)} {x}")
                df_display['Sell Loc Display'] = df_display['sell_location'].apply(lambda x: f"{get_table_icon(x)} {x}")

                # --- Define FINAL Column Names and Order ---
                column_rename_map = {
                    'item_name': 'Item', 'quality': 'Q',
                    'Buy Loc Display': 'Buy Loc',
                    'Sell Loc Display': 'Sell Loc',
                    'buy_price': 'Buy Price', 'sell_price': 'Sell Price',
                    'estimated_tax': 'Tax (Est)', 'potential_net_profit': 'Net Profit (Est)',
                    'profit_margin_percent': 'Margin %',
                    'avg_daily_volume': 'Avg Daily Vol (Sell)',
                    'opportunity_score': 'Opportunity'
                }
                final_display_order = [
                    'Item', 'Q', 'Buy Loc', 'Buy Price', 'Sell Loc', 'Sell Price',
                    'Tax (Est)', 'Net Profit (Est)', 'Margin %', 'Avg Daily Vol (Sell)',
                    'Opportunity'
                ]

                df_display = df_display.rename(columns=column_rename_map)[final_display_order]

                # --- Apply Styling ---
                styled_df = df_display.style \
                    .map(apply_style_to_icon_cell, subset=['Buy Loc', 'Sell Loc']) \
                    .background_gradient(cmap='Greens', subset=['Opportunity'], axis=0) \
                    .set_properties(**{'text-align': 'center'}) \
                    .format({
                        'Buy Price': "{:,.0f}", 'Sell Price': "{:,.0f}", 
                        'Tax (Est)': "{:,.0f}", 'Net Profit (Est)': "{:,.0f}", 
                        'Margin %': "{:.2f}%", 'Avg Daily Vol (Sell)': "{:,.0f}",
                        'Opportunity': "{:,.0f}"
                    }, na_rep="N/A")

                # --- Add Header Styling and Zebra Stripes ---
                header_style = {
                    'selector': 'th.col_heading',
                    'props': [
                        ('background-color', '#f0f0f0'),
                        ('color', '#333333'),
                        ('font-weight', 'bold'),
                        ('text-align', 'center'),
                        ('padding', '5px 10px'),
                        ('border', '1px solid #ddd'),
                        ('max-width', '100px'),
                        ('white-space', 'normal')
                    ]
                }
                zebra_style_odd = {
                    'selector': 'tr:nth-child(odd)',
                    'props': [('background-color', '#ffffff')]
                }
                zebra_style_even = {
                    'selector': 'tr:nth-child(even)',
                    'props': [('background-color', '#f9f9f9')]
                }
                center_cells_style = {
                    'selector': 'td',
                    'props': [
                        ('text-align', 'center'),
                        ('padding', '5px 10px'),
                        ('border', '1px solid #ddd'),
                        ('max-width', '100px'),
                        ('white-space', 'normal')
                    ]
                }
                styled_df = styled_df.set_table_styles([header_style, zebra_style_odd, zebra_style_even, center_cells_style], overwrite=False)

                # When displaying results, use responsive container
                if potential_scalps:
                    with results_area.container():
                        st.success(f"Found {len(potential_scalps)} potential scalps (sorted by Opportunity Score):")
                        
                        # Display dataframe without height constraint
                        st.dataframe(
                            styled_df,
                            use_container_width=True,
                            hide_index=True
                        )
                else:
                    results_area.warning("No profitable scalps found matching the criteria.")

        except ImportError as e:
            st.error(f"Import Error during analysis: {e}. Check file paths and dependencies.")
            logging.error(f"Import Error during analysis: {e}", exc_info=True)

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

if "show_register" not in st.session_state:
    st.session_state["show_register"] = False

# Check for verification token in URL
if "token" in st.query_params:
    verify_email_page()
elif st.session_state.get("authenticated", False):
    display_dashboard()
elif st.session_state.get("show_register", False):
    register_form()
else:
    login_form() 
import yaml
import logging
from pathlib import Path
import os

CONFIG_FILE_PATH = Path(__file__).parent.parent / "config" / "settings.yaml" # Assumes utils/ is one level down from root

# Hold the loaded config globally within this module after first load
_config = None
_config_loaded = False

def load_config() -> dict:
    """Loads configuration from the settings.yaml file."""
    global _config, _config_loaded
    if _config_loaded:
        return _config

    if not CONFIG_FILE_PATH.exists():
        logging.error(f"Configuration file not found at: {CONFIG_FILE_PATH}")
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE_PATH}")

    try:
        with open(CONFIG_FILE_PATH, 'r') as stream:
            _config = yaml.safe_load(stream)
        _config_loaded = True
        # Basic validation (can be expanded)
        if not _config:
            raise ValueError("Configuration file is empty or invalid.")
        if 'api' not in _config or 'base_url' not in _config['api']:
             raise ValueError("Config missing 'api.base_url'.")
        # Add more essential checks as needed
        logging.info(f"Configuration loaded successfully from {CONFIG_FILE_PATH}")
        return _config
    except yaml.YAMLError as e:
        logging.error(f"Error parsing configuration file {CONFIG_FILE_PATH}: {e}", exc_info=True)
        raise ValueError(f"Error parsing configuration file: {e}") from e
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading config: {e}", exc_info=True)
        raise # Re-raise other exceptions

def get_config() -> dict:
    """Returns the loaded configuration dictionary."""
    if not _config_loaded:
        return load_config()
    return _config

# Example usage / basic test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO) # Setup basic logging for test
    try:
        config = load_config()
        print("Config loaded successfully:")
        # print(yaml.dump(config, indent=2)) # Pretty print the loaded config
        print(f"API Base URL: {config.get('api', {}).get('base_url')}")
        print(f"Royal Cities: {config.get('locations', {}).get('royal_cities')}")
        print(f"Default Items: {len(config.get('analysis', {}).get('default_items', []))} items")
        print(f"Logging Level: {config.get('logging', {}).get('level')}")
    except (FileNotFoundError, ValueError) as e:
        print(f"Failed to load config: {e}") 
# create_hash.py
# Purpose: To generate a secure password hash for secrets.toml

from passlib.context import CryptContext
import getpass

# Use bcrypt for hashing (secure and standard)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

print("--- Password Hash Generator ---")

# Get the desired username
username = input("Enter the username (e.g., norfind): ")

# Get the password securely (it won't show while typing)
password_to_hash = getpass.getpass(f"Enter the password you want to set for '{username}': ")

# Generate the hash
hashed_password = pwd_context.hash(password_to_hash)

# Print the results clearly
print("\n--- SUCCESS! ---")
print("Add the following line inside the [credentials] section of your .streamlit/secrets.toml file:")
print("\n" + f'"{username}" = "{hashed_password}"' + "\n") # <<< This line contains the username and the hash you need
print("(Make sure the file is located at C:\\Users\\Fernando\\albion_trade_analyzer\\.streamlit\\secrets.toml)")

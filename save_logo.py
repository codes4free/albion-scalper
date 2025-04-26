import requests
import os

def download_logo():
    # Create images directory if it doesn't exist
    os.makedirs('images', exist_ok=True)
    
    # URL of the Albion Online logo
    url = 'https://assets.albiononline.com/assets/images/albion-online-logo.png'
    
    try:
        # Download the image
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Save the image
        with open('images/albion_logo_new.png', 'wb') as f:
            f.write(response.content)
        print("Logo downloaded successfully!")
    except Exception as e:
        print(f"Error downloading logo: {e}")

if __name__ == "__main__":
    download_logo() 
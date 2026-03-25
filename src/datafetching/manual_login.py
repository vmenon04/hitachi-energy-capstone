import os
import msal
from dotenv import load_dotenv

# MSAL Configuration
load_dotenv()
CLIENT_ID = os.environ.get("SHAREPOINT_CLIENT_ID") # ID of Azure app registration, required to get token for API access
SCOPES = ["https://graph.microsoft.com/Files.Read.All"] 
AUTHORITY = os.environ.get("SHAREPOINT_AUTHORITY")
CACHE_FILE = "token_cache.bin"  # where to store auth token for Azure app registration

def manual_login():
    """
    Manually logs into Azure so that we can get a token to use to access MS Graph API later, stores token to the token_cache.bin file
    """
    print("Checking for existing cache...")
    cache = msal.SerializableTokenCache() # stores memory token and account data
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache.deserialize(f.read()) # read data from our cache file if it exists
    
    # Set up Microsoft Authentication Library client, using our Azure App ID (CLIENT_ID) and the permissions that we set earlier (AUTHORITY)
    # Parses throught the data from the cache file
    app = msal.PublicClientApplication( 
        CLIENT_ID, 
        authority=AUTHORITY,
        token_cache=cache
    )

    # Check if we already have an account stored in cache
    accounts = app.get_accounts()
    if accounts:
        print(f"Found existing account: {accounts[0]['username']}")
        # if an account is found, we are done, and can exit.
        return

    # If no valid cache, perform Device Code Flow
    print("\nNo account found. Trying to log in manually.")
    # initiate_device_flow is a function that is meant to run on devices that do not have access to a web brower
    # we will log in manually via a web browser, but then a token is returned.
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "message" in flow:
        print("\n")
        print(flow["message"])
        print("\n")
    else:
        # Error handling if the manual login prompt is not given to the user.
        raise Exception(f"Could not initiate device flow: {flow.get('error_description', 'Unknown error')}")

    # waits for user to log in, and then returns the access and refresh tokens.    
    result = app.acquire_token_by_device_flow(flow)
    
    if result and "access_token" in result:
        # Save the cache file with the new tokens (including the Refresh Token)
        with open(CACHE_FILE, "w") as f:
            f.write(cache.serialize())
        print(f"\nAuthentication successful! The cache file now has the refresh tokens necessary to use MS Graph-API.")
    else:
        # Error handling if the token is not acquired from the account. 
        # Most likely if the Azure App Registration is not done properly.
        error_msg = result.get("error_description") if result else "Unknown error"
        print(f"\nERROR: Could not acquire token: {error_msg}")

if __name__ == "__main__":
    manual_login()

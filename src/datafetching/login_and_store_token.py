"""
One-time local script for personal Microsoft account setup.

Run this before the container job runs for the first time, and again whenever
the refresh token expires (~90 days of no use for personal accounts).

What it does:
  1. Prompts you to log in via device code flow in a browser.
  2. Serialises the resulting MSAL token cache (access + refresh tokens).
  3. Stores the cache as the Key Vault secret 'sharepoint-token-cache'.

The unattended container job then reads this cached token and silently
refreshes it on each run without any human interaction.

Prerequisites:
  az login                   # grants write access to Key Vault
  .env with:
    SHAREPOINT_CLIENT_ID     # from your Entra App Registration
    AZURE_KEYVAULT_URI       # e.g. https://kv<suffix>.vault.azure.net/
"""

import os
import msal
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

load_dotenv()

CLIENT_ID = os.environ["SHAREPOINT_CLIENT_ID"]
KV_URI = os.environ["AZURE_KEYVAULT_URI"]
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["https://graph.microsoft.com/Files.Read.All"]
SECRET_NAME = "sharepoint-token-cache"


def main():
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "message" not in flow:
        raise Exception(
            f"Could not initiate device flow: {flow.get('error_description', 'Unknown error')}"
        )

    print(flow["message"])

    result = app.acquire_token_by_device_flow(flow)
    if not result or "access_token" not in result:
        error = result.get("error_description", "Unknown error") if result else "No response"
        raise Exception(f"Authentication failed: {error}")

    username = result.get("id_token_claims", {}).get("preferred_username", "unknown")
    print(f"\nAuthenticated as: {username}")

    kv_client = SecretClient(vault_url=KV_URI, credential=DefaultAzureCredential())
    kv_client.set_secret(SECRET_NAME, cache.serialize())

    print(f"Token cache stored in Key Vault secret '{SECRET_NAME}'.")
    print("The container job can now run unattended until the refresh token expires (~90 days).")


if __name__ == "__main__":
    main()

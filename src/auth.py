import base64
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0,
    "base_api_url": None,
    "is_sandbox": False
}


def get_credentials() -> tuple[str, str, str, str, bool]:
    """
    Retrieves and validates eBay API credentials from the environment.
    Provides diagnostic messaging for Sandbox vs Production modes.
    """
    env_str = os.getenv("EBAY_ENV", "sandbox").strip().lower()
    is_sandbox = (env_str == "sandbox")

    if is_sandbox:
        prefix = "EBAY_SANDBOX_"
        token_endpoint = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        base_api_url = "https://api.sandbox.ebay.com"
        print(
            "[NOTICE] EBAY_ENV is set to 'sandbox'.\n"
            "         eBay's Sandbox environment only contains mock developer items and does NOT\n"
            "         have real live marketplace card inventory. To query live marketplace listings,\n"
            "         set EBAY_ENV=production in .env and provide your production eBay API keys.\n",
            file=sys.stderr
        )
    else:
        prefix = "EBAY_PROD_"
        token_endpoint = "https://api.ebay.com/identity/v1/oauth2/token"
        base_api_url = "https://api.ebay.com"

    app_id = (os.getenv(f"{prefix}APP_ID") or "").strip()
    cert_id = (os.getenv(f"{prefix}CERT_ID") or "").strip()

    if not app_id or not cert_id or app_id.startswith("your_") or cert_id.startswith("your_"):
        print(
            f"[ERROR] Missing or placeholder credentials for {prefix}APP_ID / {prefix}CERT_ID in .env.\n"
            f"        Please update .env with valid {prefix} credentials from https://developer.ebay.com.",
            file=sys.stderr
        )
        return "", "", token_endpoint, base_api_url, is_sandbox

    return app_id, cert_id, token_endpoint, base_api_url, is_sandbox


def get_access_token() -> tuple[str | None, str]:
    """
    Retrieves an OAuth application access token using client_credentials grant.
    Caches token in-memory until near expiration.
    Returns (access_token, base_api_url). If credentials are missing, returns (None, base_api_url).
    """
    now = time.time()
    if _TOKEN_CACHE["access_token"] and now < (_TOKEN_CACHE["expires_at"] - 60):
        return _TOKEN_CACHE["access_token"], _TOKEN_CACHE["base_api_url"]

    app_id, cert_id, token_endpoint, base_api_url, is_sandbox = get_credentials()

    if not app_id or not cert_id:
        return None, base_api_url

    raw_credentials = f"{app_id}:{cert_id}"
    encoded_credentials = base64.b64encode(raw_credentials.encode("utf-8")).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}"
    }

    payload = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
    }

    try:
        response = requests.post(token_endpoint, headers=headers, data=payload, timeout=15)
    except requests.RequestException as e:
        print(f"[ERROR] Failed to connect to eBay OAuth endpoint: {e}", file=sys.stderr)
        return None, base_api_url

    if response.status_code != 200:
        print(f"[ERROR] eBay OAuth Token Error (HTTP {response.status_code}): {response.text}", file=sys.stderr)
        return None, base_api_url

    data = response.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 7200)

    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at"] = now + expires_in
    _TOKEN_CACHE["base_api_url"] = base_api_url
    _TOKEN_CACHE["is_sandbox"] = is_sandbox

    return token, base_api_url

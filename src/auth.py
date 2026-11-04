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
    "base_api_url": None
}


def get_credentials():
    env_str = os.getenv("EBAY_ENV", "production").strip().lower()
    is_sandbox = env_str == "sandbox"

    if is_sandbox:
        prefix = "EBAY_SANDBOX_"
        token_endpoint = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        base_api_url = "https://api.sandbox.ebay.com"
    else:
        prefix = "EBAY_PROD_"
        token_endpoint = "https://api.ebay.com/identity/v1/oauth2/token"
        base_api_url = "https://api.ebay.com"

    app_id = os.getenv(f"{prefix}APP_ID")
    cert_id = os.getenv(f"{prefix}CERT_ID")

    if not app_id or not cert_id:
        print(f"Error: Missing {prefix}APP_ID or {prefix}CERT_ID in .env", file=sys.stderr)
        sys.exit(1)

    return app_id.strip(), cert_id.strip(), token_endpoint, base_api_url


def get_access_token() -> tuple[str, str]:
    now = time.time()
    if _TOKEN_CACHE["access_token"] and now < (_TOKEN_CACHE["expires_at"] - 60):
        return _TOKEN_CACHE["access_token"], _TOKEN_CACHE["base_api_url"]

    app_id, cert_id, token_endpoint, base_api_url = get_credentials()

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

    response = requests.post(token_endpoint, headers=headers, data=payload, timeout=15)

    if response.status_code != 200:
        print(f"OAuth Token Error (HTTP {response.status_code}): {response.text}", file=sys.stderr)
        sys.exit(1)

    data = response.json()
    token = data["access_token"]
    expires_in = data.get("expires_in", 7200)

    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at"] = now + expires_in
    _TOKEN_CACHE["base_api_url"] = base_api_url

    return token, base_api_url
import sys
import requests
from src.normalizer import verify_listing_title, is_graded


def search_ebay_listings(
    token: str,
    base_url: str,
    query_str: str,
    player_name: str,
    card_number: str,
    parallel_name: str | None = None,
    limit: int = 50
) -> list[dict]:
    """
    Queries the eBay Browse API with automatic fallback relaxation if strict search yields 0 results.
    """
    endpoint = f"{base_url}/buy/browse/v1/item_summary/search"

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json"
    }

    # Build a list of fallback queries ordered from strict to broad
    queries_to_try = [query_str]

    # Fallback 1: Strip hyphen from card number (e.g. "TTR-48" -> "TTR48" or "48")
    clean_num = str(card_number).strip().lstrip("#")
    if "-" in clean_num:
        alt_num = clean_num.replace("-", "")
        fallback_1 = query_str.replace(clean_num, alt_num)
        if fallback_1 not in queries_to_try:
            queries_to_try.append(fallback_1)

    # Fallback 2: Drop the parallel name if it's too restrictive
    if parallel_name and parallel_name in query_str:
        fallback_2 = query_str.replace(parallel_name, "").strip()
        # clean up double spaces
        fallback_2 = " ".join(fallback_2.split())
        if fallback_2 not in queries_to_try:
            queries_to_try.append(fallback_2)

    item_summaries = []
    
    for idx, q in enumerate(queries_to_try):
        if idx > 0:
            print(f"    [!] Strict query returned 0 results. Trying fallback query [{idx}] : '{q}'")

        params = {
            "q": q,
            "limit": str(min(limit, 200)),
            "sort": "newlyListed"
        }

        response = requests.get(endpoint, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            item_summaries = data.get("itemSummaries", [])
            if item_summaries:
                break
        else:
            print(f"Browse API Error: HTTP {response.status_code} - {response.text}", file=sys.stderr)

    results = []
    for item in item_summaries:
        title = item.get("title", "")

        # Use verification, but pass a slightly relaxed validator if fallback was used
        if not verify_listing_title(title, player_name, card_number, parallel_name=None):
            continue

        price_obj = item.get("price", {})
        try:
            price_val = float(price_obj.get("value", 0.0))
        except (ValueError, TypeError):
            continue

        shipping_options = item.get("shippingOptions", [])
        shipping_val = 0.0
        if shipping_options:
            ship_cost = shipping_options[0].get("shippingCost", {})
            try:
                shipping_val = float(ship_cost.get("value", 0.0))
            except (ValueError, TypeError):
                shipping_val = 0.0

        results.append({
            "title": title,
            "price": price_val,
            "shipping": shipping_val,
            "total_price": round(price_val + shipping_val, 2),
            "graded": is_graded(title),
            "url": item.get("itemWebUrl", ""),
            "item_id": item.get("itemId", "")
        })

    return results
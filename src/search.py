import sys
from typing import Optional
import requests
from src.normalizer import (
    generate_query_candidates,
    verify_listing_title,
    is_graded
)

# eBay Browse API Category IDs
SPORTS_TRADING_CARDS_CATEGORY = "212"
NON_SPORTS_TRADING_CARDS_CATEGORY = "183050"
CCG_TRADING_CARDS_CATEGORY = "183454"


def search_ebay_listings(
    token: str,
    base_url: str,
    metadata: Optional[dict] = None,
    query_str: Optional[str] = None,
    player_name: str = "",
    card_number: str = "",
    parallel_name: Optional[str] = None,
    category_id: Optional[str] = SPORTS_TRADING_CARDS_CATEGORY,
    limit: int = 50
) -> list[dict]:
    """
    Queries the eBay Browse API with progressive multi-tier fallback relaxation.
    Unlike naive search, this continues to search until verified listings are found,
    preventing empty results when sellers omit secondary keywords or use non-standard titles.
    """
    if not token:
        print("[search_ebay_listings] No valid eBay access token provided.", file=sys.stderr)
        return []

    endpoint = f"{base_url}/buy/browse/v1/item_summary/search"

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json"
    }

    # Build fallback queries
    if metadata:
        queries_to_try = generate_query_candidates(metadata, player_name, card_number)
    elif query_str:
        queries_to_try = [query_str]
        # Generate basic fallbacks if query_str provided directly
        clean_num = str(card_number).strip().lstrip("#")
        if "-" in clean_num:
            queries_to_try.append(query_str.replace(clean_num, clean_num.replace("-", "")))
        if player_name and clean_num and f"{player_name} {clean_num}" not in queries_to_try:
            queries_to_try.append(f"{player_name} {clean_num}")
    else:
        queries_to_try = [f"{player_name} {card_number}".strip()]

    verified_results = []
    seen_item_ids = set()

    for idx, q in enumerate(queries_to_try):
        if idx > 0 and not verified_results:
            print(f"    [!] Query [{idx}] trying fallback: '{q}'")

        # Try with category filter first, then without category filter if needed
        category_attempts = [category_id] if category_id else [None]
        if category_id:
            category_attempts.append(None)  # Fallback to category-agnostic

        for cat in category_attempts:
            params = {
                "q": q,
                "limit": str(min(limit, 100)),
                "sort": "newlyListed"
            }
            if cat:
                params["category_ids"] = str(cat)

            try:
                response = requests.get(endpoint, headers=headers, params=params, timeout=12)
            except requests.RequestException as e:
                print(f"[search_ebay_listings] Network error for query '{q}': {e}", file=sys.stderr)
                continue

            if response.status_code != 200:
                # If category was rejected or query errored, proceed to next attempt
                continue

            data = response.json()
            item_summaries = data.get("itemSummaries", [])
            if not item_summaries:
                continue

            # Validate listings from this response
            for item in item_summaries:
                item_id = item.get("itemId", "")
                if item_id in seen_item_ids:
                    continue

                title = item.get("title", "")
                # Use relaxed validation for later query tiers
                is_relaxed = (idx >= 2)
                if not verify_listing_title(
                    title=title,
                    player_name=player_name,
                    card_number=card_number,
                    series_name=metadata.get("series_name") if metadata else None,
                    manufacturer_name=metadata.get("manufacturer_name") if metadata else None,
                    parallel_name=parallel_name,
                    relaxed=is_relaxed
                ):
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

                seen_item_ids.add(item_id)
                verified_results.append({
                    "title": title,
                    "price": price_val,
                    "shipping": shipping_val,
                    "total_price": round(price_val + shipping_val, 2),
                    "graded": is_graded(title),
                    "url": item.get("itemWebUrl", ""),
                    "item_id": item_id,
                    "source": "ebay_api"
                })

            # If we collected enough verified results from this query, stop fallback
            if len(verified_results) >= 5:
                break

        if len(verified_results) >= 5:
            break

    return verified_results

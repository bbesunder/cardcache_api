import argparse
import os
from pathlib import Path
import sqlite3
import sys

# Ensure root directory is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import get_access_token
from src.normalizer import build_search_query
from src.search import search_ebay_listings
from src.pricing import calculate_pricing_metrics


def get_db_connection(db_path: str) -> sqlite3.Connection:
    target = Path(db_path).resolve()
    if not target.exists() or not target.is_file():
        print(f"Error: Database not found at: {target}", file=sys.stderr)
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(target))
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute("SELECT 1;")
        return conn
    except sqlite3.Error as e:
        print(f"SQLite Connection Error: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_card_metadata(conn: sqlite3.Connection, series_id: int, parallel_series_id: int | None = None) -> dict:
    cursor = conn.cursor()

    series_query = """
        SELECT 
            s.name AS series_name,
            s.year AS series_year,
            m.name AS manufacturer_name
        FROM series s
        JOIN manufacturers m ON s.manufacturerId = m.manufacturerId
        WHERE s.seriesId = ?
    """
    cursor.execute(series_query, (series_id,))
    series_row = cursor.fetchone()

    if not series_row:
        print(f"Error: No series found with seriesId = {series_id}", file=sys.stderr)
        sys.exit(1)

    metadata = {
        "series_name": series_row["series_name"],
        "series_year": series_row["series_year"] if "series_year" in series_row.keys() else None,
        "manufacturer_name": series_row["manufacturer_name"],
        "parallel_name": None
    }

    if parallel_series_id is not None:
        cursor.execute("SELECT name FROM parallel_series WHERE parallelSeriesId = ?", (parallel_series_id,))
        parallel_row = cursor.fetchone()
        if parallel_row:
            metadata["parallel_name"] = parallel_row["name"]

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Query DB metadata and fetch eBay comps via official Browse API.")
    parser.add_argument("--seriesId", type=int, required=True, help="ID from the series table")
    parser.add_argument("--parallelSeriesId", type=int, default=None, help="Optional ID from parallel_series table")
    parser.add_argument("--player", type=str, required=True, help="Player name (e.g., 'Ken Griffey Jr')")
    parser.add_argument("--number", type=str, required=True, help="Card number (e.g., '1' or 'US175')")
    parser.add_argument("--limit", type=int, default=50, help="Max results to fetch (default: 50)")

    args = parser.parse_args()

    default_db = os.getenv("DB_PATH", "")
    if not default_db:
        print("Error: DB_PATH not defined in .env", file=sys.stderr)
        sys.exit(1)

    conn = get_db_connection(default_db)
    try:
        metadata = fetch_card_metadata(conn, args.seriesId, args.parallelSeriesId)
    finally:
        conn.close()

    print("=== Resolved Database Metadata ===")
    print(f"Manufacturer : {metadata['manufacturer_name']}")
    print(f"Series       : {metadata['series_name']}")
    if metadata['series_year']:
        print(f"Year         : {metadata['series_year']}")
    print(f"Parallel     : {metadata['parallel_name'] if metadata['parallel_name'] else 'Base / None'}")
    print(f"Player       : {args.player}")
    print(f"Card Number  : #{args.number.lstrip('#')}")

    search_query = build_search_query(metadata, args.player, args.number)
    print(f"\nConstructed Query: '{search_query}'")

    token, base_url = get_access_token()
    listings = search_ebay_listings(
        token=token,
        base_url=base_url,
        query_str=search_query,
        player_name=args.player,
        card_number=args.number,
        parallel_name=metadata["parallel_name"],
        limit=args.limit
    )

    if not listings:
        print("No matching listings found.")
        return

    print(f"\nFound {len(listings)} verified listings:")
    for item in listings:
        badge = "[GRADED]" if item["graded"] else "[RAW]   "
        print(f" {badge} ${item['price']:>7.2f} (Ship: ${item['shipping']:.2f}) | {item['title']}")

    metrics = calculate_pricing_metrics(listings)

    print("\n=== Pricing Summary ===")
    raw = metrics["raw"]
    if raw["count"] > 0:
        print(f"Raw Median : ${raw['median']:.2f} (Avg: ${raw['average']:.2f} across {raw['count']} items)")
        print(f"Raw Range  : ${raw['min']:.2f} - ${raw['max']:.2f}")
    else:
        print("Raw Comps  : None found")

    graded = metrics["graded"]
    if graded["count"] > 0:
        print(f"Graded Med : ${graded['median']:.2f} (Avg: ${graded['average']:.2f} across {graded['count']} items)")
        print(f"Graded Rng : ${graded['min']:.2f} - ${graded['max']:.2f}")
    else:
        print("Graded Comps: None found")


if __name__ == "__main__":
    main()
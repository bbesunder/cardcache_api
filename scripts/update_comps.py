import argparse
import os
from pathlib import Path
import sqlite3
import sys
from typing import Union, Optional

# Ensure root directory is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.service import CardPricingService
from src.normalizer import build_search_query


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


def fetch_card_metadata(conn: sqlite3.Connection, series_id: str, parallel_series_id: Optional[str] = None) -> dict:
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
    cursor.execute(series_query, (str(series_id),))
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
        # Table in card cache database is 'series_parallels'
        cursor.execute("SELECT name FROM series_parallels WHERE parallelSeriesId = ?", (str(parallel_series_id),))
        parallel_row = cursor.fetchone()
        if parallel_row:
            metadata["parallel_name"] = parallel_row["name"]

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Query DB card metadata and fetch comps across eBay API and web scrapers.")
    parser.add_argument("--seriesId", type=str, required=True, help="ID from the series table (e.g., '121159')")
    parser.add_argument("--parallelSeriesId", type=str, default=None, help="Optional ID from series_parallels table")
    parser.add_argument("--player", type=str, required=True, help="Player name (e.g., 'Ken Griffey Jr')")
    parser.add_argument("--number", type=str, required=True, help="Card number (e.g., '1' or 'US175')")
    parser.add_argument("--source", type=str, choices=["all", "ebay", "sportscardspro", "sportlots"], default="all",
                        help="Data source: 'ebay', 'sportscardspro', 'sportlots', or 'all' (default: all)")
    parser.add_argument("--limit", type=int, default=50, help="Max results to fetch (default: 50)")
    parser.add_argument("--no-history", action="store_true", help="Skip fetching individual historical transaction history")

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
    print(f"\nPrimary Query: '{search_query}'")
    print(f"Source(s)    : {args.source}")

    service = CardPricingService()
    results = service.get_card_comps(
        metadata=metadata,
        player_name=args.player,
        card_number=args.number,
        sources=[args.source],
        limit=args.limit,
        include_historical=not args.no_history
    )

    benchmarks = results.get("benchmarks", [])
    if benchmarks:
        print("\n=== Market Condition Benchmarks ===")
        for b in benchmarks:
            source = b.get("source", "benchmark")
            print(f"[{source.upper()}] Card: {b['card_title']} | Set: {b['set_name']}")
            ungraded = f"${b['ungraded_price']:.2f}" if b.get('ungraded_price') is not None else "N/A"
            grade9 = f"${b['grade9_price']:.2f}" if b.get('grade9_price') is not None else "N/A"
            psa10 = f"${b['psa10_price']:.2f}" if b.get('psa10_price') is not None else "N/A"
            print(f"  -> Ungraded / Ask : {ungraded}")
            if b.get('grade9_price') is not None or b.get('psa10_price') is not None:
                print(f"  -> Grade 9        : {grade9}")
                print(f"  -> PSA 10         : {psa10}")
            if b.get('active_quantity'):
                print(f"  -> Active Lots    : {b['active_quantity']} in stock")
            if b.get("url"):
                print(f"  -> Link           : {b['url']}")

    listings = results.get("listings", [])
    if not listings and not benchmarks:
        print("\nNo matching listings or benchmarks found.")
        return

    if listings:
        print(f"\nFound {len(listings)} verified comp transactions:")
        for item in listings[:20]:
            badge = "[GRADED]" if item["graded"] else "[RAW]   "
            source_tag = f"[{item.get('source', 'unknown')}]"
            date_tag = f" ({item['date']})" if item.get("date") else ""
            ship_text = f" (Ship: ${item.get('shipping', 0.0):.2f})" if item.get('shipping') else ""
            print(f" {badge} {source_tag} ${item['price']:>7.2f}{ship_text}{date_tag} | {item['title'][:80]}")

        if len(listings) > 20:
            print(f" ... and {len(listings) - 20} more transactions.")

    metrics = results.get("metrics", {})
    print("\n=== Pricing Summary ===")
    raw = metrics.get("raw", {})
    if raw.get("count", 0) > 0:
        print(f"Raw Median   : ${raw['median']:.2f} (Avg: ${raw['average']:.2f}, Trimmed Avg: ${raw['trimmed_mean']:.2f} across {raw['count']} items)")
        print(f"Raw Range    : ${raw['min']:.2f} - ${raw['max']:.2f}")
    else:
        print("Raw Comps    : None found")

    graded = metrics.get("graded", {})
    if graded.get("count", 0) > 0:
        print(f"Graded Median: ${graded['median']:.2f} (Avg: ${graded['average']:.2f}, Trimmed Avg: ${graded['trimmed_mean']:.2f} across {graded['count']} items)")
        print(f"Graded Range : ${graded['min']:.2f} - ${graded['max']:.2f}")
    else:
        print("Graded Comps : None found")


if __name__ == "__main__":
    main()

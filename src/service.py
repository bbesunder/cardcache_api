from __future__ import annotations

import sys
from typing import Optional, Any

from src.auth import get_access_token
from src.pricing import calculate_pricing_metrics
from src.search import search_ebay_listings
from src.scrapers.sportscardspro import SportsCardsProScraper
from src.scrapers.sportlots import SportlotsScraper


class CardPricingService:
    """
    Unified multi-source pricing service for CardCache.
    Coordinates between eBay's official Browse API and web scrapers
    (such as SportsCardsPro) to deliver comprehensive market comps,
    condition benchmarks (Ungraded, Grade 9, PSA 10), and statistical metrics.
    """

    def __init__(self):
        self.sportscardspro_scraper = SportsCardsProScraper()
        self.sportlots_scraper = SportlotsScraper()

    def get_card_comps(
        self,
        metadata: dict,
        player_name: str,
        card_number: str,
        sources: Optional[list] = None,
        limit: int = 50,
        include_historical: bool = True
    ) -> dict:
        """
        Fetches card comparables across requested sources.

        :param metadata: Card metadata dict (manufacturer_name, series_name, series_year, parallel_name)
        :param player_name: Athlete / Subject name (e.g., 'Ken Griffey Jr')
        :param card_number: Card number (e.g., '1' or 'US175')
        :param sources: List of sources to query ('ebay', 'sportscardspro', 'sportlots', or 'all')
        :param limit: Max listings per source
        :param include_historical: Whether to fetch individual historical sales transactions from scrapers
        :return: Standardized dictionary containing benchmarks, listings, and statistical summary.
        """
        if sources is None:
            sources = ["all"]

        sources_lower = [s.lower() for s in sources]
        query_all = "all" in sources_lower

        all_listings = []
        benchmarks = []
        sources_queried = []

        # 1. SportsCardsPro Scraper
        if query_all or "sportscardspro" in sources_lower:
            sources_queried.append("sportscardspro")
            try:
                # Fetch condition valuations (Ungraded, Grade 9, PSA 10)
                card_benchmarks = self.sportscardspro_scraper.search_card_valuation(
                    metadata=metadata,
                    player_name=player_name,
                    card_number=card_number
                )
                if card_benchmarks:
                    benchmarks.extend(card_benchmarks)

                # Fetch recent completed transactions
                if include_historical:
                    scp_sales = self.sportscardspro_scraper.fetch_recent_sales(
                        metadata=metadata,
                        player_name=player_name,
                        card_number=card_number,
                        limit=limit
                    )
                    all_listings.extend(scp_sales)
            except Exception as e:
                print(f"[CardPricingService] SportsCardsPro error: {e}", file=sys.stderr)

        # 2. Sportlots Scraper (Base cards, commons, low-price benchmarks)
        if query_all or "sportlots" in sources_lower:
            sources_queried.append("sportlots")
            try:
                sl_benchmarks = self.sportlots_scraper.search_card_valuation(
                    metadata=metadata,
                    player_name=player_name,
                    card_number=card_number
                )
                if sl_benchmarks:
                    benchmarks.extend(sl_benchmarks)

                if include_historical:
                    sl_sales = self.sportlots_scraper.fetch_recent_sales(
                        metadata=metadata,
                        player_name=player_name,
                        card_number=card_number,
                        limit=limit
                    )
                    all_listings.extend(sl_sales)
            except Exception as e:
                print(f"[CardPricingService] Sportlots error: {e}", file=sys.stderr)

        # 3. eBay Browse API
        if query_all or "ebay" in sources_lower:
            sources_queried.append("ebay_api")
            token, base_url = get_access_token()
            if token:
                try:
                    ebay_listings = search_ebay_listings(
                        token=token,
                        base_url=base_url,
                        metadata=metadata,
                        player_name=player_name,
                        card_number=card_number,
                        parallel_name=metadata.get("parallel_name"),
                        limit=limit
                    )
                    all_listings.extend(ebay_listings)
                except Exception as e:
                    print(f"[CardPricingService] eBay API error: {e}", file=sys.stderr)
            else:
                print("[CardPricingService] Skipping eBay Browse API due to missing/invalid credentials.", file=sys.stderr)

        # 4. Compute statistical pricing aggregates
        pricing_metrics = calculate_pricing_metrics(all_listings)

        return {
            "player_name": player_name,
            "card_number": card_number,
            "metadata": metadata,
            "benchmarks": benchmarks,
            "listings": all_listings,
            "metrics": pricing_metrics,
            "sources_queried": sources_queried
        }

from __future__ import annotations

import re
import sys
try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    import requests
    HAS_CURL_CFFI = False
from typing import Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

from src.scrapers.base import BaseCardScraper
from src.normalizer import (
    clean_card_number,
    build_search_query,
    verify_listing_title,
    is_graded
)


class SportsCardsProScraper(BaseCardScraper):
    """
    Scraper for SportsCardsPro (PriceCharting's dedicated trading cards marketplace).
    Collects live condition-based valuations (Ungraded, Grade 9, PSA 10)
    and detailed recent completed transaction history without requiring API keys.
    """

    BASE_URL = "https://www.sportscardspro.com"
    SEARCH_ENDPOINT = f"{BASE_URL}/search-products"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        if HAS_CURL_CFFI:
            self.session = cffi_requests.Session(impersonate="chrome")
        else:
            self.session = requests.Session()
            self.session.headers.update(self.DEFAULT_HEADERS)

    @property
    def source_name(self) -> str:
        return "sportscardspro"

    @staticmethod
    def _parse_price(text: Optional[str]) -> Optional[float]:
        """Parses a price string like '$5,850.00' or '$91.00' into a float."""
        if not text:
            return None
        match = re.search(r'\$?([\d,]+\.?\d*)', text)
        if match:
            clean = match.group(1).replace(',', '')
            try:
                return float(clean)
            except ValueError:
                return None
        return None

    def search_card_valuation(
        self,
        metadata: dict,
        player_name: str,
        card_number: str
    ) -> list[dict]:
        """
        Searches SportsCardsPro for card valuation benchmarks.
        Returns all matching variants (Base, Star Rookie, Parallels, etc.).
        """
        clean_num = clean_card_number(card_number)

        # Build search queries (specific first, then broader)
        queries = [
            build_search_query(metadata, player_name, clean_num, tier=2),
            build_search_query(metadata, player_name, clean_num, tier=3),
            f"{player_name} {clean_num}"
        ]

        seen_urls = set()
        results = []

        for query in queries:
            if not query:
                continue

            params = {
                "type": "prices",
                "q": query
            }

            try:
                resp = self.session.get(self.SEARCH_ENDPOINT, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                print(f"[SportsCardsPro] Search request error for '{query}': {e}", file=sys.stderr)
                continue

            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", {"id": "games_table"})
            if not table:
                continue

            rows = table.find_all("tr")[1:]  # Skip header
            for row in rows:
                title_td = row.find("td", class_="title")
                if not title_td:
                    continue

                links = title_td.find_all("a")
                card_title = links[0].get_text(strip=True) if links else title_td.get_text(strip=True)
                set_name = links[1].get_text(strip=True) if len(links) >= 2 else ""

                if links and links[0].get("href"):
                    product_url = urljoin(self.BASE_URL, links[0]["href"])
                else:
                    product_url = ""

                if product_url in seen_urls:
                    continue

                # Verify card title against player, card number, series name, and manufacturer
                if not verify_listing_title(
                    f"{card_title} {set_name}",
                    player_name=player_name,
                    card_number=clean_num,
                    series_name=metadata.get("series_name"),
                    manufacturer_name=metadata.get("manufacturer_name"),
                    parallel_name=metadata.get("parallel_name"),
                    relaxed=True
                ):
                    continue

                ungraded_td = row.find("td", class_="used_price")
                grade9_td = row.find("td", class_="cib_price")
                psa10_td = row.find("td", class_="new_price")

                ungraded_price = self._parse_price(ungraded_td.get_text(strip=True)) if ungraded_td else None
                grade9_price = self._parse_price(grade9_td.get_text(strip=True)) if grade9_td else None
                psa10_price = self._parse_price(psa10_td.get_text(strip=True)) if psa10_td else None

                seen_urls.add(product_url)
                results.append({
                    "card_title": card_title,
                    "set_name": set_name,
                    "ungraded_price": ungraded_price,
                    "grade9_price": grade9_price,
                    "psa10_price": psa10_price,
                    "url": product_url,
                    "source": self.source_name
                })

            if results:
                # If we found valid results, stop trying fallback queries
                break

        return results

    def fetch_recent_sales(
        self,
        metadata: dict,
        player_name: str,
        card_number: str,
        limit: int = 25
    ) -> list[dict]:
        """
        Fetches individual completed sale transactions for the card.
        Queries the product page directly and parses the transaction history table.
        """
        valuations = self.search_card_valuation(metadata, player_name, card_number)
        if not valuations:
            return []

        # Target the primary product URL
        target_card = valuations[0]
        product_url = target_card.get("url")
        if not product_url:
            return []

        try:
            resp = self.session.get(product_url, timeout=self.timeout)
        except requests.RequestException as e:
            print(f"[SportsCardsPro] Error fetching product page: {e}", file=sys.stderr)
            return []

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table", class_="hoverable-rows")

        sales = []
        for table in tables:
            for row in table.find_all("tr"):
                title_td = row.find("td", class_="title")
                date_td = row.find("td", class_="date")
                price_td = row.find("td", class_="numeric")

                if not title_td or not price_td:
                    continue

                raw_title = title_td.get_text(strip=True).replace("[eBay]", "").strip()
                date_str = date_td.get_text(strip=True) if date_td else ""
                price_val = self._parse_price(price_td.get_text(strip=True))

                if not verify_listing_title(
                    raw_title,
                    player_name=player_name,
                    card_number=card_number,
                    series_name=metadata.get("series_name"),
                    manufacturer_name=metadata.get("manufacturer_name"),
                    parallel_name=metadata.get("parallel_name"),
                    relaxed=True
                ):
                    continue

                if price_val is not None and price_val > 0:
                    item_graded = is_graded(raw_title)
                    sales.append({
                        "title": raw_title,
                        "date": date_str,
                        "price": price_val,
                        "shipping": 0.0,
                        "total_price": price_val,
                        "graded": item_graded,
                        "url": product_url,
                        "source": f"{self.source_name}_sales"
                    })

                if len(sales) >= limit:
                    break
            if len(sales) >= limit:
                break

        return sales

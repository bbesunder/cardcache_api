from __future__ import annotations

import json
import re
import sys
from typing import Optional
import requests

from src.scrapers.base import BaseCardScraper
from src.normalizer import (
    clean_card_number,
    build_search_query,
    verify_listing_title
)


class SportlotsScraper(BaseCardScraper):
    """
    Scraper for Sportlots.com (the largest marketplace for base cards, commons,
    semi-stars, and vintage checklist cards).

    Uses Sportlots' internal search and pricing endpoints:
    - /b/ajax/LoadSearchNbrData.tpl (initializes search criteria)
    - /b/ajax/PullSearchData.tpl (fetches card list, active inventory quantities, and lowest ask)
    - /b/ajax/ChartResults.tpl (fetches historical sales averages by condition: NM, EXNM, EX, VG)
    """

    BASE_URL = "https://www.sportlots.com"
    SEARCH_INIT_ENDPOINT = f"{BASE_URL}/b/ajax/LoadSearchNbrData.tpl"
    SEARCH_DATA_ENDPOINT = f"{BASE_URL}/b/ajax/PullSearchData.tpl"
    CHART_DATA_ENDPOINT = f"{BASE_URL}/b/ajax/ChartResults.tpl"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": f"{BASE_URL}/b/ui/search.tpl",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Condition map: ID -> Name
    CONDITIONS = {
        "1": "NM",
        "2": "EXNM",
        "3": "EX",
        "4": "VG",
        "5": "GOOD"
    }

    def __init__(self, timeout: int = 12):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        # Warm up session
        try:
            self.session.get(f"{self.BASE_URL}/b/ui/search.tpl", timeout=timeout)
        except Exception:
            pass

    @property
    def source_name(self) -> str:
        return "sportlots"

    @staticmethod
    def _parse_price(text: Optional[str]) -> Optional[float]:
        """Parses a price string like '$110.02' into a float."""
        if not text:
            return None
        match = re.search(r'\$?([\d,]+\.?\d*)', text)
        if match:
            clean = match.group(1).replace(',', '')
            try:
                val = float(clean)
                return val if val > 0 else None
            except ValueError:
                return None
        return None

    def _query_search_table(self, query: str) -> tuple[list[dict], int]:
        """
        Executes Sportlots' two-step search AJAX workflow.
        Returns (list_of_search_rows, search_nbr).
        """
        params_init = {
            "searchval": query,
            "searchnbr": "0",
            "BoxChecked": "undefined",
            "AttrType": "null",
            "AttrSeq": "null",
            "SellerID": "null"
        }

        try:
            r1 = self.session.get(self.SEARCH_INIT_ENDPOINT, params=params_init, timeout=self.timeout)
            if r1.status_code != 200:
                return [], 0
            data1 = json.loads(r1.text)
            search_nbr = int(data1.get("SearchNbr", 0))
            if not search_nbr:
                return [], 0
        except Exception as e:
            print(f"[Sportlots] Init error for '{query}': {e}", file=sys.stderr)
            return [], 0

        params_data = {
            "searchnbr": str(search_nbr),
            "dir": "F",
            "cpg": "0"
        }

        try:
            r2 = self.session.get(self.SEARCH_DATA_ENDPOINT, params=params_data, timeout=self.timeout)
            if r2.status_code != 200:
                return [], search_nbr
            data2 = json.loads(r2.text)
            return data2.get("searchTable", []), search_nbr
        except Exception as e:
            print(f"[Sportlots] Fetch error for search #{search_nbr}: {e}", file=sys.stderr)
            return [], search_nbr

    def search_card_valuation(
        self,
        metadata: dict,
        player_name: str,
        card_number: str
    ) -> list[dict]:
        """
        Searches Sportlots for card valuations and active lowest ask prices.
        Matches against metadata to avoid manufacturer/set collisions.
        """
        clean_num = clean_card_number(card_number)

        queries = [
            build_search_query(metadata, player_name, clean_num, tier=2),
            build_search_query(metadata, player_name, clean_num, tier=3),
            f"{player_name} {clean_num}"
        ]

        seen_keys = set()
        results = []

        for query in queries:
            if not query:
                continue

            search_table, search_nbr = self._query_search_table(query)
            if not search_table:
                continue

            for row in search_table:
                set_nbr = row.get("SetNbr")
                seq_nbr = row.get("SeqNbr")
                key = f"{set_nbr}:{seq_nbr}"
                if key in seen_keys:
                    continue

                set_info = row.get("SetInfo", "")
                card_info = row.get("CardInfo", "")
                full_title = f"{card_info} {set_info}"

                # Strict validation against brand, player, and card number
                if not verify_listing_title(
                    title=full_title,
                    player_name=player_name,
                    card_number=clean_num,
                    series_name=metadata.get("series_name"),
                    manufacturer_name=metadata.get("manufacturer_name"),
                    parallel_name=metadata.get("parallel_name"),
                    relaxed=True
                ):
                    continue

                low_price = self._parse_price(row.get("LowPrice"))
                tot_qty = row.get("TotQty", 0)
                detail_url = f"{self.BASE_URL}/b/ui/details.tpl?set={set_nbr}&seq={seq_nbr}"

                # Query historical NM and EXNM sales averages if available
                nm_avg = None
                try:
                    r_chart = self.session.get(
                        f"{self.CHART_DATA_ENDPOINT}?setval={set_nbr}&seqval={seq_nbr}&timespan=TwelveM&cond=1",
                        timeout=self.timeout
                    )
                    if r_chart.status_code == 200:
                        c_data = json.loads(r_chart.text)
                        nm_avg = self._parse_price(c_data.get("AvgCards"))
                except Exception:
                    nm_avg = None

                seen_keys.add(key)
                results.append({
                    "card_title": card_info,
                    "set_name": set_info,
                    "ungraded_price": low_price or nm_avg,
                    "grade9_price": None,
                    "psa10_price": None,
                    "active_quantity": tot_qty,
                    "historical_nm_avg": nm_avg,
                    "set_nbr": set_nbr,
                    "seq_nbr": seq_nbr,
                    "url": detail_url,
                    "source": self.source_name
                })

            if results:
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
        Fetches historical sales data points across conditions (NM, EXNM, EX, VG)
        from Sportlots sales history tracking.
        """
        valuations = self.search_card_valuation(metadata, player_name, card_number)
        if not valuations:
            return []

        target = valuations[0]
        set_nbr = target.get("set_nbr")
        seq_nbr = target.get("seq_nbr")
        detail_url = target.get("url", "")
        title_base = f"{target.get('card_title')} ({target.get('set_name')})"

        if not set_nbr or not seq_nbr:
            return []

        sales = []
        for cond_id, cond_name in [("1", "NM"), ("2", "EXNM"), ("3", "EX")]:
            try:
                url = f"{self.CHART_DATA_ENDPOINT}?setval={set_nbr}&seqval={seq_nbr}&timespan=TwelveM&cond={cond_id}"
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code != 200:
                    continue
                data = json.loads(resp.text)
                chart_table = data.get("ChartTable", [])
                for pt in chart_table:
                    price_val = self._parse_price(str(pt.get("yVal", "")))
                    date_val = str(pt.get("xVal", "")).strip()
                    if price_val and price_val > 0:
                        sales.append({
                            "title": f"{title_base} [{cond_name}]",
                            "date": date_val,
                            "price": price_val,
                            "shipping": 0.0,
                            "total_price": price_val,
                            "graded": False,
                            "url": detail_url,
                            "source": f"{self.source_name}_sales"
                        })
                    if len(sales) >= limit:
                        break
            except Exception as e:
                print(f"[Sportlots] Error reading sales chart for {cond_name}: {e}", file=sys.stderr)

            if len(sales) >= limit:
                break

        return sales

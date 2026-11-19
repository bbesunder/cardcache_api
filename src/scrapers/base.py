from abc import ABC, abstractmethod


class BaseCardScraper(ABC):
    """
    Abstract base class for secondary trading card auction and sales scrapers.
    Standardizes output format across different marketplace platforms.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the data provider (e.g. 'sportscardspro', 'comc', etc.)."""
        raise NotImplementedError

    @abstractmethod
    def search_card_valuation(
        self,
        metadata: dict,
        player_name: str,
        card_number: str
    ) -> list[dict]:
        """
        Searches for card price benchmarks across conditions (Ungraded, Grade 9, PSA 10).
        Returns a list of matching card variant valuations:
        [
            {
                "card_title": str,
                "set_name": str,
                "ungraded_price": float | None,
                "grade9_price": float | None,
                "psa10_price": float | None,
                "url": str,
                "source": str
            }, ...
        ]
        """
        pass

    @abstractmethod
    def fetch_recent_sales(
        self,
        metadata: dict,
        player_name: str,
        card_number: str,
        limit: int = 20
    ) -> list[dict]:
        """
        Fetches individual completed sale transactions.
        Returns a list of standardized listing objects compatible with calculate_pricing_metrics:
        [
            {
                "title": str,
                "price": float,
                "shipping": float,
                "total_price": float,
                "graded": bool,
                "url": str,
                "date": str,
                "source": str
            }, ...
        ]
        """
        pass

import statistics


def calculate_pricing_metrics(items: list[dict]) -> dict:
    """
    Computes statistical pricing aggregates for raw and graded card pools.
    """
    raw_sales = [i["price"] for i in items if not i["graded"]]
    graded_sales = [i["price"] for i in items if i["graded"]]

    def summarize(prices: list[float]) -> dict:
        if not prices:
            return {
                "count": 0,
                "average": None,
                "median": None,
                "min": None,
                "max": None
            }
        return {
            "count": len(prices),
            "average": round(statistics.mean(prices), 2),
            "median": round(statistics.median(prices), 2),
            "min": round(min(prices), 2),
            "max": round(max(prices), 2)
        }

    return {
        "raw": summarize(raw_sales),
        "graded": summarize(graded_sales),
        "total_verified_comps": len(items)
    }
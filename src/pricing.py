import statistics


def filter_iqr_outliers(prices: list[float]) -> tuple[list[float], int]:
    """
    Filters statistical outliers using the Interquartile Range (IQR) method.
    Returns the cleaned list of prices and the count of outliers removed.
    """
    if len(prices) < 4:
        return sorted(prices), 0

    sorted_p = sorted(prices)
    n = len(sorted_p)
    q1 = sorted_p[n // 4]
    q3 = sorted_p[(3 * n) // 4]
    iqr = q3 - q1

    if iqr == 0:
        return sorted_p, 0

    lower_bound = max(0.0, q1 - 1.5 * iqr)
    upper_bound = q3 + 1.5 * iqr

    cleaned = [p for p in sorted_p if lower_bound <= p <= upper_bound]
    outliers_removed = len(sorted_p) - len(cleaned)
    return cleaned if cleaned else sorted_p, outliers_removed


def summarize_prices(prices: list[float]) -> dict:
    """
    Computes statistical pricing aggregates for a price array,
    including outlier detection and standard deviation.
    """
    if not prices:
        return {
            "count": 0,
            "average": None,
            "median": None,
            "min": None,
            "max": None,
            "trimmed_mean": None,
            "std_dev": None,
            "outliers_removed": 0
        }

    cleaned_prices, outliers_count = filter_iqr_outliers(prices)

    avg_val = round(statistics.mean(prices), 2)
    med_val = round(statistics.median(prices), 2)
    min_val = round(min(prices), 2)
    max_val = round(max(prices), 2)
    trimmed_mean = round(statistics.mean(cleaned_prices), 2) if cleaned_prices else avg_val
    std_dev = round(statistics.stdev(prices), 2) if len(prices) >= 2 else 0.0

    return {
        "count": len(prices),
        "average": avg_val,
        "median": med_val,
        "min": min_val,
        "max": max_val,
        "trimmed_mean": trimmed_mean,
        "std_dev": std_dev,
        "outliers_removed": outliers_count
    }


def calculate_pricing_metrics(items: list[dict], use_total_price: bool = True) -> dict:
    """
    Computes statistical pricing aggregates for raw and graded card pools.
    Allows using total_price (price + shipping) or base price.
    """
    def get_price(item: dict) -> float:
        if use_total_price and "total_price" in item and item["total_price"] is not None:
            return float(item["total_price"])
        return float(item.get("price") or 0.0)

    raw_sales = [get_price(i) for i in items if not i.get("graded", False) and get_price(i) > 0]
    graded_sales = [get_price(i) for i in items if i.get("graded", False) and get_price(i) > 0]
    all_sales = raw_sales + graded_sales

    return {
        "raw": summarize_prices(raw_sales),
        "graded": summarize_prices(graded_sales),
        "overall": summarize_prices(all_sales),
        "total_verified_comps": len(items)
    }

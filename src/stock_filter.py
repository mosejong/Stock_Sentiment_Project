import os


def _parse_stock_env(name: str) -> set[str]:
    raw_value = os.getenv(name, "")
    return {
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    }


def filter_stocks(stocks: dict[str, str]) -> dict[str, str]:
    include = _parse_stock_env("STOCK_INCLUDE")
    exclude = _parse_stock_env("STOCK_EXCLUDE")

    filtered = {}
    for name, ticker in stocks.items():
        keys = {str(name), str(ticker)}
        if include and not keys.intersection(include):
            continue
        if exclude and keys.intersection(exclude):
            continue
        filtered[name] = ticker

    return filtered


def describe_stock_filter(total_count: int, active_count: int) -> str:
    include = os.getenv("STOCK_INCLUDE", "").strip()
    exclude = os.getenv("STOCK_EXCLUDE", "").strip()

    if include:
        return f"STOCK_INCLUDE={include} -> {active_count}/{total_count} stocks"
    if exclude:
        return f"STOCK_EXCLUDE={exclude} -> {active_count}/{total_count} stocks"
    return f"all stocks -> {active_count}/{total_count} stocks"

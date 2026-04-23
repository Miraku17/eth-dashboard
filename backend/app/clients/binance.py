from dataclasses import dataclass

import httpx

BINANCE_BASE_URL = "https://api.binance.com"
VALID_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


@dataclass(slots=True)
class Kline:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time_ms: int


class BinanceClient:
    """Thin async wrapper around Binance public klines endpoint."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 500,
    ) -> list[Kline]:
        if interval not in VALID_INTERVALS:
            raise ValueError(f"unsupported interval: {interval}")

        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        resp = await self._http.get("/api/v3/klines", params=params)
        resp.raise_for_status()
        return [_row_to_kline(row) for row in resp.json()]


def _row_to_kline(row: list) -> Kline:
    return Kline(
        open_time_ms=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time_ms=int(row[6]),
    )

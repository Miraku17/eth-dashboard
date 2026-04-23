from typing import Literal

from pydantic import BaseModel, Field

Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]


class Candle(BaseModel):
    time: int = Field(description="open time, unix seconds")
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    candles: list[Candle]

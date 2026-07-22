import asyncio
import inspect
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import yfinance as yf

from core.models import Candle, Exchange, InstrumentType, Quote, Tick

logger = logging.getLogger(__name__)

YAHOO_SYMBOL_MAP: dict[str, str] = {
    "NSE:NIFTY50-INDEX": "^NSEI",
    "NSE:NIFTYBANK-INDEX": "^NSEBANK",
    "NSE:FINNIFTY-INDEX": "NIFTY_FIN_SERVICE.NS",
    "BSE:SENSEX-INDEX": "^BSESN",
    "NSE:MIDCPNIFTY-INDEX": "^NSEMDCP50",
    "NSE:INDIAVIX-INDEX": "^INDIAVIX",
    "NSE:NIFTYIT-INDEX": "^CNXIT",
    "NSE:NIFTYPHARMA-INDEX": "^CNXPHARMA",
    "NSE:NIFTYAUTO-INDEX": "^CNXAUTO",
    "NSE:NIFTYFMCG-INDEX": "^CNXFMCG",
    "NSE:NIFTYMETAL-INDEX": "^CNXMETAL",
    "NSE:NIFTYREALTY-INDEX": "^CNXREALTY",
    "NSE:NIFTYENERGY-INDEX": "^CNXENERGY",
    "NSE:NIFTYMEDIA-INDEX": "^CNXMEDIA",
    "NSE:NIFTYPSUBANK-INDEX": "^CNXPSUBANK",
    "NSE:NIFTYPVTBANK-INDEX": "^NIFTY_PVT_BANK",
    "NSE:NIFTYCONSR-INDEX": "^CNXCONSUM",
    "NSE:NIFTYOILGAS-INDEX": "^CNXOILGAS",
    "NSE:NIFTYDIVOP-INDEX": "^CNXDIVOP",
    "NSE:NIFTYGSEC-INDEX": "^CNXGSEQ",
}

YAHOO_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "1d": "1d",
    "1wk": "1wk",
    "1mo": "1mo",
}


def _to_yahoo(symbol: str) -> str:
    mapped = YAHOO_SYMBOL_MAP.get(symbol)
    if mapped:
        return mapped
    clean = symbol.split(":")[-1]
    clean = clean.removesuffix("-EQ")
    return f"{clean}.NS"


def _from_yahoo(yahoo_symbol: str) -> str:
    for our_sym, y_sym in YAHOO_SYMBOL_MAP.items():
        if y_sym == yahoo_symbol:
            return our_sym
    return yahoo_symbol.replace(".NS", "")


async def fetch_quotes(symbols: list[str]) -> list[Quote]:
    yahoo_symbols = [_to_yahoo(s) for s in symbols]
    try:
        loop = asyncio.get_running_loop()
        tickers = await loop.run_in_executor(None, lambda: yf.Tickers(" ".join(yahoo_symbols)))
        quotes = []
        for i, s in enumerate(symbols):
            ys = yahoo_symbols[i]
            t = tickers.tickers.get(ys)
            if not t:
                continue
            info = t.info if hasattr(t, "info") else {}
            if not info:
                continue
            quotes.append(Quote(
                symbol=s,
                exchange=Exchange.NSE,
                last_price=float(info.get("currentPrice", info.get("regularMarketPrice", 0))),
                open=float(info.get("open", info.get("regularMarketOpen", 0))),
                high=float(info.get("dayHigh", info.get("regularDayHigh", 0))),
                low=float(info.get("dayLow", info.get("regularDayLow", 0))),
                close=float(info.get("previousClose", info.get("regularMarketPreviousClose", 0))),
                volume=int(info.get("volume", info.get("regularMarketVolume", 0))),
                bid=float(info.get("bid", 0)),
                ask=float(info.get("ask", 0)),
                timestamp=datetime.now(UTC),
                broker="yahoo",
                instrument_type=InstrumentType.EQ,
                strike_price=None,
                expiry_date=None,
                option_type=None,
            ))
        return quotes
    except Exception as e:
        logger.warning("Yahoo fetch_quotes failed: %s", e)
        return []


async def fetch_historical(symbol: str, interval: str = "1d", period: str = "7d") -> list[Candle]:
    ys = _to_yahoo(symbol)
    y_interval = YAHOO_INTERVAL_MAP.get(interval, interval)
    if y_interval not in ("1m", "5m", "15m", "30m", "60m", "1d", "1wk", "1mo"):
        y_interval = "1d"
    try:
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, lambda: yf.Ticker(ys))
        hist = await loop.run_in_executor(None, lambda: ticker.history(period=period, interval=y_interval))
        if hist.empty:
            return []
        candles = []
        for idx, row in hist.iterrows():
            candles.append(Candle(
                symbol=symbol,
                exchange=Exchange.NSE,
                interval=interval,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
                timestamp=idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
            ))
        return candles
    except Exception as e:
        logger.warning("Yahoo fetch_historical(%s) failed: %s", symbol, e)
        return []


async def stream(
    symbols: list[str],
    on_tick: Callable[[Tick], None],
    interval_seconds: float = 1.0,
    running_flag: asyncio.Event | None = None,
):
    if running_flag is None:
        running_flag = asyncio.Event()
        running_flag.set()

    import httpx

    yahoo_symbols = [_to_yahoo(s) for s in symbols]

    async with httpx.AsyncClient(timeout=5) as client:
        while running_flag.is_set():
            try:
                url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={','.join(yahoo_symbols)}"
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    await asyncio.sleep(interval_seconds)
                    continue
                data = resp.json()
                results = data.get("quoteResponse", {}).get("result", [])
                for item in results:
                    ys = item.get("symbol", "")
                    try:
                        idx = yahoo_symbols.index(ys)
                    except ValueError:
                        continue
                    s = symbols[idx]
                    ltp = float(item.get("regularMarketPrice", 0))
                    if ltp == 0:
                        continue
                    prev_close = float(item.get("regularMarketPreviousClose", ltp))
                    tick = Tick(
                        symbol=s, exchange=Exchange.NSE,
                        last_price=ltp,
                        bid=float(item.get("bid", 0)),
                        ask=float(item.get("ask", 0)),
                        volume=int(item.get("regularMarketVolume", 0)),
                        oi=0,
                        change=round(ltp - prev_close, 2),
                        change_pct=round((ltp - prev_close) / max(prev_close, 0.01) * 100, 2),
                        timestamp=datetime.now(UTC), broker="yahoo",
                    )
                    if inspect.iscoroutinefunction(on_tick):
                        await on_tick(tick)
                    else:
                        on_tick(tick)
            except httpx.TimeoutException:
                logger.warning("Yahoo quote API timed out")
            except Exception as e:
                logger.warning("Yahoo stream error: %s", e)
            await asyncio.sleep(interval_seconds)

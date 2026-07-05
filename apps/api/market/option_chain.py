import datetime
import logging
import random
from typing import Any

import httpx

from market.cache import market_cache

logger = logging.getLogger(__name__)

STRIKE_INTERVALS: dict[str, int] = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "SENSEX": 100}
LOT_SIZES: dict[str, int] = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "SENSEX": 20}
NSE_INDICES = {"NIFTY", "BANKNIFTY", "FINNIFTY"}


class OptionChainEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    async def get_option_chain(self, symbol: str, expiry: str = "") -> dict:
        cache_key = f"option_chain:{symbol.upper()}:{expiry}"
        cached = market_cache.get_option_chain(cache_key)
        if cached:
            return {**cached, "is_simulated": cached.get("is_simulated", True)}

        data = await self._fetch_nse_option_chain(symbol.upper())
        if data:
            data["is_simulated"] = False
            market_cache.put_option_chain(cache_key, data)
            return data

        logger.warning("Option chain unavailable for %s (NSE fetch failed)", symbol)
        return {}

    async def get_expiries(self, symbol: str) -> list[str]:
        cache_key = f"expiries:{symbol.upper()}"
        cached = market_cache.get_expiries(cache_key)
        if cached:
            return cached

        expiries = await self._fetch_nse_expiries(symbol.upper())
        if expiries:
            market_cache.put_expiries(cache_key, expiries)
            return expiries

        return [self._next_expiry(symbol.upper())]

    async def _fetch_nse_option_chain(self, symbol: str) -> dict | None:
        if symbol not in NSE_INDICES:
            return None
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                client.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "application/json, text/plain, */*",
                })
                await client.get("https://www.nseindia.com")
                resp = await client.get(f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}")
                if resp.status_code != 200:
                    return None
                data = resp.json()
                records = data.get("records", {})
                raw_expiries = records.get("expiryDates", [])
                raw_data = records.get("data", [])
                if not raw_expiries or not raw_data:
                    return None
                expiries = []
                for e in raw_expiries:
                    try:
                        dt = datetime.datetime.strptime(e, "%d-%b-%Y").strftime("%d%b").upper()
                        expiries.append(dt)
                    except Exception:
                        expiries.append(e.upper().replace("-", ""))
                option_chain = []
                strikes_seen = set()
                for row in raw_data:
                    strike = row.get("strikePrice", 0)
                    if not strike or strike in strikes_seen:
                        continue
                    strikes_seen.add(strike)
                    ce = row.get("CE") or {}
                    pe = row.get("PE") or {}
                    option_chain.append({
                        "strike": strike,
                        "call": {
                            "ltp": ce.get("lastPrice", 0),
                            "change": ce.get("change", 0),
                            "change_pct": ce.get("pChange", 0),
                            "bid": ce.get("bidprice", 0),
                            "ask": ce.get("askPrice", 0),
                            "volume": ce.get("totalTradedVolume", 0),
                            "oi": ce.get("openInterest", 0),
                            "iv": ce.get("impliedVolatility", 0),
                        },
                        "put": {
                            "ltp": pe.get("lastPrice", 0),
                            "change": pe.get("change", 0),
                            "change_pct": pe.get("pChange", 0),
                            "bid": pe.get("bidprice", 0),
                            "ask": pe.get("askPrice", 0),
                            "volume": pe.get("totalTradedVolume", 0),
                            "oi": pe.get("openInterest", 0),
                            "iv": pe.get("impliedVolatility", 0),
                        },
                    })
                if option_chain and expiries:
                    logger.info("NSE option chain fetched for %s (%d strikes)", symbol, len(option_chain))
                    return {"optionChain": option_chain, "expiries": expiries}
        except Exception as e:
            logger.warning("NSE option chain fetch failed for %s: %s", symbol, e)
        return None

    async def _fetch_nse_expiries(self, symbol: str) -> list[str] | None:
        if symbol not in NSE_INDICES:
            return None
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                client.headers.update({
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "application/json",
                })
                await client.get("https://www.nseindia.com")
                resp = await client.get(f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}")
                if resp.status_code != 200:
                    return None
                data = resp.json()
                records = data.get("records", {})
                raw_expiries = records.get("expiryDates", [])
                if not raw_expiries:
                    return None
                expiries = []
                for e in raw_expiries:
                    try:
                        dt = datetime.datetime.strptime(e, "%d-%b-%Y").strftime("%d%b").upper()
                        expiries.append(dt)
                    except Exception:
                        expiries.append(e.upper().replace("-", ""))
                return expiries[:5]
        except Exception as e:
            logger.warning("NSE expiries fetch failed for %s: %s", symbol, e)
        return None

    def calculate_pcr(self, chain_data: dict) -> float:
        option_chain = chain_data.get("optionChain", [])
        total_call_oi = 0
        total_put_oi = 0
        for row in option_chain:
            total_call_oi += (row.get("call") or {}).get("oi", 0)
            total_put_oi += (row.get("put") or {}).get("oi", 0)
        if total_call_oi == 0:
            return 0.0
        return round(total_put_oi / total_call_oi, 2)

    def calculate_max_pain(self, chain_data: dict) -> float:
        option_chain = chain_data.get("optionChain", [])
        if not option_chain:
            return 0.0
        min_pain = float("inf")
        max_pain_strike = 0.0
        for row in option_chain:
            strike = row.get("strike", 0)
            call = row.get("call") or {}
            put = row.get("put") or {}
            call_oi = call.get("oi", 0)
            put_oi = put.get("oi", 0)
            pain = 0
            for other in option_chain:
                other_strike = other.get("strike", 0)
                other_call = other.get("call") or {}
                other_put = other.get("put") or {}
                if other_strike > strike:
                    pain += (other_strike - strike) * other_call.get("oi", 0)
                elif other_strike < strike:
                    pain += (strike - other_strike) * other_put.get("oi", 0)
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = strike
        return max_pain_strike

    def calculate_oi_change(self, current: dict, previous: dict | None) -> list[dict]:
        if not previous:
            return []
        current_chain = {r["strike"]: r for r in current.get("optionChain", [])}
        previous_chain = {r["strike"]: r for r in previous.get("optionChain", [])}
        result = []
        for strike, cur_row in current_chain.items():
            prev_row = previous_chain.get(strike)
            if prev_row:
                result.append({
                    "strike": strike,
                    "call_oi_change": (cur_row.get("call") or {}).get("oi", 0) - (prev_row.get("call") or {}).get("oi", 0),
                    "put_oi_change": (cur_row.get("put") or {}).get("oi", 0) - (prev_row.get("put") or {}).get("oi", 0),
                })
        return result

option_chain_engine = OptionChainEngine()

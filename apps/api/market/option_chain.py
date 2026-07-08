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

        data = await self._fetch_fyers_option_chain(symbol.upper())
        if data:
            data["is_simulated"] = False
            market_cache.put_option_chain(cache_key, data)
            return data

        logger.warning("Option chain unavailable for %s (NSE + Fyers fallback failed)", symbol)
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

        expiries = await self._fetch_fyers_expiries(symbol.upper())
        if expiries:
            market_cache.put_expiries(cache_key, expiries)
            return expiries

        return [self._next_expiry(symbol.upper())]

    def _next_expiry(self, symbol: str) -> str:
        today = datetime.date.today()
        # NSE weekly expiry is Thursday
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        next_thu = today + datetime.timedelta(days=days_ahead)
        return next_thu.strftime("%d%b").upper()

    async def _fetch_nse_option_chain(self, symbol: str) -> dict | None:
        if symbol not in NSE_INDICES:
            return None
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
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
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
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

    async def _fetch_fyers_option_chain(self, symbol: str) -> dict | None:
        fyers_map = {"NIFTY": "NSE:NIFTY50-INDEX", "BANKNIFTY": "NSE:NIFTYBANK-INDEX", "FINNIFTY": "NSE:FINNIFTY-INDEX", "SENSEX": "BSE:SENSEX-INDEX"}
        fyers_symbol = fyers_map.get(symbol.upper(), f"NSE:{symbol.upper()}")
        try:
            from core.db import get_supabase
            from core.security import decrypt_broker_credentials
            supabase = get_supabase()
            active = supabase.table("broker_credentials").select("*").eq("broker", "fyers").eq("is_active", True).limit(1).execute()
            if not active.data:
                return None
            cred = active.data[0]
            client_id = decrypt_broker_credentials(cred.get("encrypted_api_key", ""))
            raw_token = decrypt_broker_credentials(cred.get("encrypted_access_token", ""))
            if not client_id or not raw_token:
                return None

            async with httpx.AsyncClient(timeout=10) as client:
                headers = {"Authorization": f"{client_id}:{raw_token}", "Content-Type": "application/json"}
                params = {"symbol": fyers_symbol, "strikecount": 50, "timestamp": ""}
                resp = await client.get(
                    "https://api-t1.fyers.in/data/options-chain-v3",
                    params=params,
                    headers=headers,
                )
                data = resp.json()
                if data.get("s") != "ok" and data.get("code") != 200:
                    return None
                chain = data.get("data", {})
                raw_options = chain.get("optionsChain", [])
                raw_expiry_data = chain.get("expiryData", [])

                expiries = []
                for e in raw_expiry_data:
                    if isinstance(e, dict):
                        date_str = e.get("date", "")
                        try:
                            dt = datetime.datetime.strptime(date_str, "%d-%m-%Y")
                            expiries.append(dt.strftime("%d%b").upper())
                        except Exception:
                            expiries.append(date_str.replace("-", ""))

                by_strike: dict[int, dict[str, dict]] = {}
                for row in raw_options:
                    strike = row.get("strike_price", 0)
                    if strike < 0:
                        continue
                    opt_type = row.get("option_type", "")
                    if opt_type not in ("CE", "PE"):
                        continue
                    by_strike.setdefault(strike, {})[opt_type] = row

                option_chain = []
                for strike in sorted(by_strike):
                    ce = by_strike[strike].get("CE", {})
                    pe = by_strike[strike].get("PE", {})
                    option_chain.append({
                        "strike": strike,
                        "call": {
                            "ltp": ce.get("ltp", 0),
                            "change": ce.get("ltpch", 0),
                            "change_pct": ce.get("ltpchp", 0),
                            "bid": ce.get("bid", 0),
                            "ask": ce.get("ask", 0),
                            "volume": ce.get("volume", 0),
                            "oi": ce.get("oi", 0),
                            "iv": ce.get("iv", 0),
                        },
                        "put": {
                            "ltp": pe.get("ltp", 0),
                            "change": pe.get("ltpch", 0),
                            "change_pct": pe.get("ltpchp", 0),
                            "bid": pe.get("bid", 0),
                            "ask": pe.get("ask", 0),
                            "volume": pe.get("volume", 0),
                            "oi": pe.get("oi", 0),
                            "iv": pe.get("iv", 0),
                        },
                    })

                if option_chain and expiries:
                    logger.info("Fyers option chain fetched for %s (%d strikes)", symbol, len(option_chain))
                    return {"optionChain": option_chain, "expiries": expiries}
        except Exception as e:
            logger.warning("Fyers option chain fetch failed for %s: %s", symbol, e)
        return None

    async def _fetch_fyers_expiries(self, symbol: str) -> list[str] | None:
        chain = await self._fetch_fyers_option_chain(symbol)
        if chain:
            return chain.get("expiries", [])
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

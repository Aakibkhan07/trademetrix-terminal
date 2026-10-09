import datetime
import logging

import httpx

from market.cache import market_cache

logger = logging.getLogger(__name__)

STRIKE_INTERVALS: dict[str, int] = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100}
NSE_INDICES = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
SUPPORTED_INDICES = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}

_INDEX_ALIASES = {
    "NIFTY50-INDEX": "NIFTY",
    "NIFTYBANK-INDEX": "BANKNIFTY",
    "FINNIFTY-INDEX": "FINNIFTY",
    "MIDCPNIFTY-INDEX": "MIDCPNIFTY",
    "SENSEX-INDEX": "SENSEX",
}


def normalize_index_symbol(symbol: str) -> str:
    """Map display symbols (e.g. 'NSE:NIFTY50-INDEX' / 'NIFTY50-INDEX')
    to the short names the data providers understand ('NIFTY')."""
    s = symbol.upper().strip()
    for prefix in ("NSE:", "BSE:", "NFO:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return _INDEX_ALIASES.get(s, s)


def _fmt_expiry(raw: str) -> str:
    """NSE sends '13-Oct-2026'; the rest of this module and the UI use '13OCT'."""
    try:
        return datetime.datetime.strptime(raw, "%d-%b-%Y").strftime("%d%b").upper()
    except (ValueError, TypeError):
        return str(raw).upper().replace("-", "")


def _num(leg: dict, *names: str) -> float:
    """First key that is present AND non-null.

    `leg.get(name, 0)` is not enough on the v3 payload: NSE renamed bid/ask to
    buyPrice1/sellPrice1 and sends the old names as explicit nulls, so the default
    never fires and None leaks into the payload. Same trap as `dict.get(key, default)`
    against a SQL NULL -- the key is present, the default does not apply.
    """
    for name in names:
        value = leg.get(name)
        if value is not None:
            return value
    return 0


def _leg(d: dict) -> dict:
    """Normalise one CE/PE leg of an NSE chain row to the internal shape."""
    return {
        "ltp": _num(d, "lastPrice"),
        "change": _num(d, "change"),
        "change_pct": _num(d, "pChange", "PChange"),
        # buyPrice1/sellPrice1 are the current names; bidprice/askPrice are kept as
        # fallbacks because v3 answers null for them on every leg measured (216/216).
        "bid": _num(d, "buyPrice1", "bidprice", "bidPrice"),
        "ask": _num(d, "sellPrice1", "askPrice", "askprice"),
        "volume": _num(d, "totalTradedVolume"),
        "oi": _num(d, "openInterest"),
        "iv": _num(d, "impliedVolatility"),
    }


def _nse_client() -> httpx.AsyncClient:
    """Client shaped for nseindia.com: primed cookie jar, browser-ish headers."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(45.0, connect=15.0),
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/option-chain",
        },
    )


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
        symbol = normalize_index_symbol(symbol)
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

        # No simulated fallback. This used to call `_generate_simulated_chain` and return a chain
        # built from a closed-form formula — `call ltp = max(100 - dist*15, 1)`, `oi = 500000`,
        # approximate greeks — labelled only `is_simulated: True`, which nothing downstream reads.
        # The `/trade` workspace therefore showed a fabricated 19-strike ladder with round-number
        # premiums as though it were a market, and a trader could size a live position off it.
        #
        # That is the same violation the v1.7.0 real-data contract removed from the candle path,
        # where `_generate_simulated_candles` was deleted because a backtest must never run on
        # fabricated data. The same rule has to hold for the chain: an option premium is a price
        # someone trades against, so inventing one is worse than showing none. The generator is
        # kept for tests that assert on its shape, and it is not on any request path.
        logger.warning("Option chain unavailable for %s (NSE + Fyers fallback failed)", symbol)
        return {}

    async def get_expiries(self, symbol: str) -> list[str]:
        symbol = normalize_index_symbol(symbol)
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
            # One client for the whole sequence: NSE is cookie-gated, so the priming GET
            # and the two API calls must share a session or the API calls answer 403.
            #
            # 5s was also too tight. The API calls themselves measure 37-59ms, but the
            # priming GET occasionally exceeds 20s on its own, and a client-wide timeout
            # took the entire chain down with it -- which is what surfaced to the UI as a
            # 503 on /marketdata/option-chain. connect is separated because a slow TCP
            # handshake to nseindia.com is a different failure from a slow response.
            async with _nse_client() as client:
                await client.get("https://www.nseindia.com")
                # NSE retired /api/option-chain-indices; it now answers 404 "Resource not
                # found" (measured 2026-10-09). Two replacements, both measured:
                #   /api/option-chain-contract-info -> {expiryDates, strikePrice}
                #   /api/option-chain-v3            -> records.data, and it REQUIRES an
                #       expiry. Without one it returns HTTP 200 with 0 rows, so an absent
                #       expiry parameter fails silently rather than loudly.
                # _expiries_from, not _fetch_nse_expiries: v3 needs NSE's wire form
                # ('13-Oct-2026'). The latter returns display codes for the UI.
                expiries_raw = await self._expiries_from(client, symbol)
                if not expiries_raw:
                    return None
                return await self._fetch_nse_v3(client, symbol, expiries_raw[0])
        except Exception as e:
            logger.warning("NSE option chain fetch failed for %s: %s", symbol, e)
        return None

    async def _fetch_nse_v3(
        self, client: httpx.AsyncClient, symbol: str, expiry: str
    ) -> dict | None:
        """Fetch one expiry from NSE's v3 endpoint.

        Kept separate from the caller so the request shape is testable without a
        network, and so a fallback chain can be added later without touching this.
        """
        try:
            resp = await client.get(
                "https://www.nseindia.com/api/option-chain-v3",
                params={"type": "Indices", "symbol": symbol, "expiry": expiry},
            )
            if resp.status_code != 200:
                logger.info("NSE v3 option chain %s returned HTTP %s", symbol,
                            resp.status_code)
                return None
            data = resp.json()
            records = data.get("records", {})
            raw_data = records.get("data", [])
            if not raw_data:
                return None
            expiries = [_fmt_expiry(e) for e in records.get("expiryDates", [])]
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
                    "call": _leg(ce),
                    "put": _leg(pe),
                })
            if option_chain and expiries:
                logger.info("NSE option chain fetched for %s (%d strikes, expiry %s)",
                            symbol, len(option_chain), expiry)
                return {"optionChain": option_chain, "expiries": expiries}
        except Exception as e:
            logger.warning("NSE v3 option chain fetch failed for %s: %s", symbol, e)
        return None

    async def _fetch_nse_expiries(
        self, symbol: str, client: httpx.AsyncClient | None = None
    ) -> list[str] | None:
        """Expiry codes for an index, newest first, capped at 5.

        `client` is accepted so the chain fetch can share its primed NSE session.
        Standing alone (the /expiries route) this opens its own client.
        """
        if symbol not in NSE_INDICES:
            return None
        try:
            if client is not None:
                raw = await self._expiries_from(client, symbol)
            else:
                async with _nse_client() as own:
                    await own.get("https://www.nseindia.com")
                    raw = await self._expiries_from(own, symbol)
            if not raw:
                return None
            return [_fmt_expiry(e) for e in raw]
        except Exception as e:
            logger.warning("NSE expiries fetch failed for %s: %s", symbol, e)
        return None

    async def _expiries_from(self, client: httpx.AsyncClient, symbol: str) -> list[str] | None:
        """Expiries in NSE's own wire format ('13-Oct-2026'), not the UI's '13OCT'.

        The chain fetch needs this form for the v3 `expiry` parameter, while
        `_fetch_nse_expiries` hands the display codes to the UI. Keeping the raw form
        here is what stops the two from being confused: passing '13OCT' to v3 returns
        HTTP 200 with zero rows, so it would look like an empty chain rather than a bug.
        """
        resp = await client.get(
            "https://www.nseindia.com/api/option-chain-contract-info",
            params={"symbol": symbol},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Measured shape is {"expiryDates": [...], "strikePrice": [...]} -- expiryDates is
        # at the TOP level here, not under records as it was on the retired endpoint.
        raw_expiries = data.get("expiryDates") or []
        if not raw_expiries:
            return None
        return list(raw_expiries)[:5] or None

    async def _fetch_fyers_option_chain(self, symbol: str) -> dict | None:
        fyers_map = {"NIFTY": "NSE:NIFTY50-INDEX", "BANKNIFTY": "NSE:NIFTYBANK-INDEX", "FINNIFTY": "NSE:FINNIFTY-INDEX", "MIDCPNIFTY": "NSE:MIDCPNIFTY-INDEX", "SENSEX": "BSE:SENSEX-INDEX"}
        fyers_symbol = fyers_map.get(symbol.upper(), f"NSE:{symbol.upper()}")
        try:
            from core.db import async_supabase, get_supabase
            from core.security import decrypt_broker_credentials
            supabase = get_supabase()
            active = await async_supabase(lambda: supabase.table("broker_credentials").select("*").eq("broker", "fyers").eq("is_active", True).execute())
            if not active.data:
                return None
            client_id = None
            raw_token = None
            for cred in active.data:
                try:
                    client_id = decrypt_broker_credentials(cred.get("encrypted_api_key", ""))
                    raw_token = decrypt_broker_credentials(cred.get("encrypted_access_token", ""))
                    if client_id and raw_token:
                        break
                except Exception:
                    continue
            if not client_id or not raw_token:
                return None

            from brokers.fyers_http import get_transport
            tr = get_transport(client_id, raw_token)
            params = {"symbol": fyers_symbol, "strikecount": 50, "timestamp": ""}
            resp = await tr.request(
                "GET",
                "/data/options-chain-v3",
                params=params,
                cache_ttl=10.0,
                caller="option_chain",
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
                        expiries.append(date_str.replace("-", "").upper())

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

    def _generate_simulated_chain(self, symbol: str) -> dict | None:
        symbol = normalize_index_symbol(symbol)
        if symbol.upper() not in SUPPORTED_INDICES:
            return None
        base_prices = {"NIFTY": 24000, "BANKNIFTY": 51000, "FINNIFTY": 21000, "SENSEX": 81000}
        base = base_prices.get(symbol.upper(), 24000)
        strike_interval = STRIKE_INTERVALS.get(symbol.upper(), 100)
        atm_round = round(base / strike_interval) * strike_interval
        strikes = list(range(atm_round - 9 * strike_interval, atm_round + 10 * strike_interval, strike_interval))
        today = datetime.datetime.now(datetime.timezone.utc)
        expiry = today + datetime.timedelta(days=(3 - today.weekday()) % 7 + 28)
        expiries = [expiry.strftime("%d%b").upper()]
        option_chain = []
        days_to_expiry = max((expiry - today).days, 1)
        sqrt_t = (days_to_expiry / 365) ** 0.5

        def _approx_greeks(is_call: bool, strike: float) -> dict:
            moneyness = (base - strike) / strike
            d1 = moneyness / max(sqrt_t, 0.01)
            d2 = d1 - 0.2 * sqrt_t
            from math import erf
            nd1 = 0.5 * (1 + erf(d1 / 2 ** 0.5))
            nd2 = 0.5 * (1 + erf(d2 / 2 ** 0.5))
            delta = nd1 if is_call else nd1 - 1
            gamma = 0.4 / max(base * 0.01, 1)
            theta = -0.1
            vega = base * 0.001
            return {"delta": round(delta, 4), "gamma": round(gamma, 6), "theta": round(theta, 4), "vega": round(vega, 4)}

        for strike in strikes:
            dist = abs(strike - atm_round) / strike_interval
            ce_iv = 14.0 + dist * 1.5
            pe_iv = 14.0 + dist * 1.5
            if strike >= atm_round:
                ce_ltp = round(max(100 - dist * 15, 1), 2)
                pe_ltp = round(max(5 - dist * 2, 0.1), 2)
            else:
                pe_ltp = round(max(100 - dist * 15, 1), 2)
                ce_ltp = round(max(5 - dist * 2, 0.1), 2)
            option_chain.append({
                "strike": strike,
                "call": {"ltp": ce_ltp, "change": round(ce_ltp * 0.02, 2), "change_pct": 2.0, "bid": round(ce_ltp * 0.98, 2), "ask": round(ce_ltp * 1.02, 2), "volume": int(10000 * (1 - dist * 0.08)), "oi": int(500000 * (1 - dist * 0.05)), "iv": round(ce_iv, 2), **_approx_greeks(True, strike)},
                "put": {"ltp": pe_ltp, "change": round(pe_ltp * 0.02, 2), "change_pct": 2.0, "bid": round(pe_ltp * 0.98, 2), "ask": round(pe_ltp * 1.02, 2), "volume": int(10000 * (1 - dist * 0.08)), "oi": int(500000 * (1 - dist * 0.05)), "iv": round(pe_iv, 2), **_approx_greeks(False, strike)},
            })
        if option_chain and expiries:
            return {"optionChain": option_chain, "expiries": expiries, "mock": True}
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

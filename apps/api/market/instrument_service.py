"""Runtime instrument resolution — options buying strategies.

Resolves lot sizes, strike steps, nearest weekly expiry, and option symbol
construction at runtime from live option-chain data, falling back to constants.
"""
import logging
from datetime import UTC, datetime
from typing import Optional

from core.constants import LOT_SIZES, MONTH_CODES, STRIKE_INTERVALS, get_weekly_expiry
from market.option_chain import option_chain_engine

logger = logging.getLogger(__name__)


class InstrumentService:
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

    def lot_size(self, index: str) -> int:
        return LOT_SIZES.get(index.upper(), 65)

    def strike_step(self, index: str) -> int:
        return STRIKE_INTERVALS.get(index.upper(), 50)

    async def nearest_weekly_expiry(self, index: str) -> str:
        index = index.upper()
        try:
            expiries = await option_chain_engine.get_expiries(index)
            if expiries:
                raw = expiries[0]
                year = datetime.now(UTC).year
                dt = datetime.strptime(f"{raw}{year}", "%d%b%Y")
                if dt.date() < datetime.now(UTC).date():
                    dt = dt.replace(year=year + 1)
                return dt.strftime("%d%b%Y").upper()
        except Exception as exc:
            logger.debug("Option chain expiry fallback for %s: %s", index, exc)
        expiry_date = get_weekly_expiry(index)
        return expiry_date.strftime("%d%b%Y").upper()

    def option_symbol(self, index: str, expiry: str, strike: float, option_type: str) -> str:
        index = index.upper()
        opt = option_type.upper()
        try:
            dt = datetime.strptime(expiry, "%d%b%Y")
            yy = str(dt.year)[-2:]
            month_code = MONTH_CODES[dt.month]
            return f"NSE:{index}{yy}{month_code}{int(strike)}{opt}"
        except Exception:
            return f"{index}{expiry}{int(strike)}{opt}"

    async def option_ltp(self, index: str, expiry: str, strike: float, option_type: str) -> float:
        try:
            chain = await option_chain_engine.get_option_chain(index.upper(), expiry)
            if not chain:
                return 0.0
            key = "call" if option_type.upper() == "CE" else "put"
            for row in chain.get("optionChain", []):
                if row.get("strike") == strike:
                    return row.get(key, {}).get("ltp", 0.0)
        except Exception:
            pass
        return 0.0

    def iv_percentile(self, index: str) -> Optional[float]:
        logger.warning("IV percentile/rank not available for %s — no historical IV tracking", index)
        return None

    async def strikes(self, index: str) -> list[float]:
        try:
            chain = await option_chain_engine.get_option_chain(index.upper())
            if not chain:
                return []
            return [float(r["strike"]) for r in chain.get("optionChain", [])]
        except Exception:
            return []

    async def days_to_expiry(self, index: str, expiry: str) -> int:
        try:
            dt = datetime.strptime(expiry, "%d%b%Y")
            return max((dt - datetime.now(UTC)).days, 1)
        except Exception:
            return 7

    async def option_iv(self, index: str, expiry: str, strike: float, option_type: str) -> float:
        try:
            chain = await option_chain_engine.get_option_chain(index.upper(), expiry)
            if not chain:
                return 0.0
            key = "call" if option_type.upper() == "CE" else "put"
            for row in chain.get("optionChain", []):
                if row.get("strike") == strike:
                    return float(row.get(key, {}).get("iv", 0.0))
        except Exception:
            pass
        return 0.0


instrument_service = InstrumentService()

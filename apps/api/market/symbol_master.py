import asyncio
import logging
from datetime import UTC, date, datetime

import httpx

from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)


class SymbolMaster:
    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._fo_cache: dict[str, dict] = {}
        self._fo_sync_task: asyncio.Task | None = None

    async def sync_nse_bhavcopy(self, trade_date: date | None = None) -> int:
        trade_date = trade_date or date.today()
        url = "https://nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
        count = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                return 0

            data = resp.json()
            supabase = get_supabase()

            for item in data.get("data", []):
                symbol = item.get("symbol", "")
                if not symbol:
                    continue

                row = {
                    "symbol": symbol,
                    "exchange": "NSE",
                    "broker": "master",
                    "broker_symbol": symbol,
                    "token": symbol,
                    "instrument_type": "EQ",
                    "lot_size": 1,
                    "tick_size": 0.05,
                    "segment": "EQ",
                    "last_updated": trade_date.isoformat(),
                }
                try:
                    await async_supabase(lambda: supabase.table("symbol_master").upsert(row, on_conflict=["broker", "token"]).execute())
                except Exception:
                    pass
                count += 1

        return count

    async def sync_broker_instruments(self, broker: str) -> int:
        count = 0
        supabase = get_supabase()

        if broker == "fyers":
            count = await self._sync_fyers_instruments(supabase)
        elif broker == "dhan":
            count = await self._sync_dhan_instruments(supabase)
        elif broker == "zerodha":
            count = await self._sync_zerodha_instruments(supabase)

        return count

    async def _sync_fyers_instruments(self, supabase) -> int:
        url = "https://public.fyers.in/symboldumps/NSE_CM.txt"
        count = 0
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return 0
            lines = resp.text.strip().split("\n")
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) < 7:
                    continue
                row = {
                    "symbol": parts[1].strip(),
                    "exchange": "NSE",
                    "broker": "fyers",
                    "broker_symbol": parts[1].strip(),
                    "token": parts[0].strip(),
                    "instrument_type": parts[4].strip(),
                    "lot_size": int(parts[5]) if parts[5].isdigit() else 1,
                    "tick_size": float(parts[6]) if parts[6].replace(".", "", 1).isdigit() else 0.05,
                    "segment": "EQ",
                    "last_updated": date.today().isoformat(),
                }
                try:
                    await async_supabase(lambda: supabase.table("symbol_master").upsert(row, on_conflict=["broker", "token"]).execute())
                except Exception:
                    pass
                count += 1
        return count


    async def resolve_symbol(self, canonical: str, broker: str) -> str | None:
        supabase = get_supabase()
        try:
            result = await async_supabase(lambda: supabase.table("symbol_master").select("broker_symbol").eq("symbol", canonical).eq("broker", broker).maybe_single().execute())
            if result.data:
                return result.data["broker_symbol"]
        except Exception:
            pass
        return canonical

    async def resolve_to_canonical(self, broker_symbol: str, broker: str) -> str | None:
        supabase = get_supabase()
        try:
            result = await async_supabase(lambda: supabase.table("symbol_master").select("symbol").eq("broker_symbol", broker_symbol).eq("broker", broker).maybe_single().execute())
            if result.data:
                return result.data["symbol"]
        except Exception as e:
            logger.warning("Symbol lookup failed: %s", e)
        return broker_symbol

    async def start_auto_sync(self) -> None:
        if self._fo_sync_task is None or self._fo_sync_task.done():
            self._fo_sync_task = asyncio.create_task(self._auto_sync_loop())
            logger.info("SymbolMaster auto-sync started")

    async def stop_auto_sync(self) -> None:
        if self._fo_sync_task and not self._fo_sync_task.done():
            self._fo_sync_task.cancel()
            try:
                await self._fo_sync_task
            except asyncio.CancelledError:
                pass
            self._fo_sync_task = None
            logger.info("SymbolMaster auto-sync stopped")

    async def _auto_sync_loop(self) -> None:
        while True:
            try:
                now = datetime.now(UTC)
                target = now.replace(hour=2, minute=30, second=0, microsecond=0)
                if now > target:
                    target = target.replace(day=target.day + 1)
                delay = (target - now).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)
                count = await self.sync_fo_symbols()
                logger.info("Auto-synced %d F&O symbols", count)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Auto-sync error: %s", e)
                await asyncio.sleep(3600)

    async def sync_fo_symbols(self) -> int:
        count = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://www.nseindia.com/api/fo-sec-list",
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                )
                if resp.status_code != 200:
                    return 0
                data = resp.json()
                supabase = get_supabase()
                for item in data:
                    symbol = item.get("symbol", "")
                    if not symbol:
                        continue
                    row = {
                        "symbol": symbol,
                        "exchange": "NFO",
                        "broker": "master",
                        "broker_symbol": symbol,
                        "token": f"{symbol}-NFO",
                        "instrument_type": "FUT",
                        "lot_size": item.get("lotSize", 1),
                        "tick_size": 0.05,
                        "segment": "FO",
                        "last_updated": date.today().isoformat(),
                    }
                    self._fo_cache[symbol] = {
                        "symbol": symbol,
                        "exchange": "NFO",
                        "instrument_type": "FUT",
                        "lot_size": item.get("lotSize", 1),
                    }
                    try:
                        await async_supabase(lambda: supabase.table("symbol_master").upsert(row, on_conflict=["broker", "token"]).execute())
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert symbol row: %s", e)
                logger.info("Synced %d F&O symbols from NSE", count)
        except Exception as e:
            logger.warning("F&O sync failed: %s", e)
        return count

    async def get_broker_symbol(self, canonical: str, broker: str) -> str | None:
        if broker == "master":
            return canonical
        cache_key = f"broker_symbol:{canonical}:{broker}"
        if cache_key in self._cache:
            return self._cache[cache_key].get("broker_symbol")
        result = await self.resolve_symbol(canonical, broker)
        if result:
            self._cache[cache_key] = {"broker_symbol": result}
        return result

    def get_symbol_info(self, symbol: str) -> dict | None:
        info = self._fo_cache.get(symbol.upper())
        if info:
            return info
        if symbol.upper() in self._cache:
            return self._cache[symbol.upper()]
        return None

    def search_symbols(self, query: str, instrument_type: str | None = None, limit: int = 20) -> list[dict]:
        q = query.upper()
        results = []
        for sym, info in self._fo_cache.items():
            if q in sym:
                if instrument_type and info.get("instrument_type") != instrument_type:
                    continue
                results.append(info)
                if len(results) >= limit:
                    break
        return results


symbol_master = SymbolMaster()

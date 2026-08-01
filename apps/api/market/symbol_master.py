import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, date, datetime, timedelta

import httpx

from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)


class SymbolMaster:
    def __init__(self):
        self._cache: OrderedDict = OrderedDict()
        self._fo_cache: OrderedDict = OrderedDict()
        self._fo_sync_task: asyncio.Task | None = None
        self._cache_max = 10000
        self._fo_cache_max = 120000
        self._batch_size = 200

    def _cache_put(self, key: str, value: dict) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    def _cache_get(self, key: str) -> dict | None:
        val = self._cache.get(key)
        if val is not None:
            self._cache.move_to_end(key)
        return val

    def _fo_cache_put(self, key: str, value: dict) -> None:
        self._fo_cache[key] = value
        self._fo_cache.move_to_end(key)
        while len(self._fo_cache) > self._fo_cache_max:
            self._fo_cache.popitem(last=False)

    def _fo_cache_get(self, key: str) -> dict | None:
        val = self._fo_cache.get(key)
        if val is not None:
            self._fo_cache.move_to_end(key)
        return val

    async def _batch_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        supabase = get_supabase()
        count = 0
        for i in range(0, len(rows), self._batch_size):
            batch = rows[i:i + self._batch_size]
            try:
                await async_supabase(lambda b=batch: supabase.table("symbol_master").upsert(b).execute())
                count += len(batch)
            except Exception:
                for row in batch:
                    try:
                        await async_supabase(lambda r=row: supabase.table("symbol_master").upsert(r).execute())
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert symbol row: %s", e)
        return count

    async def sync_nse_bhavcopy(self, trade_date: date | None = None) -> int:
        trade_date = trade_date or date.today()
        url = "https://nseindia.com/api/equity-stockIndices?index=NIFTY%2050"

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
            rows = []
            for item in data.get("data", []):
                symbol = item.get("symbol", "")
                if not symbol:
                    continue
                rows.append({
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
                })
        return await self._batch_upsert(rows)

    async def sync_broker_instruments(self, broker: str) -> int:
        if broker == "fyers":
            return await self._sync_fyers_instruments()
        elif broker == "dhan":
            return await self._sync_dhan_instruments()
        elif broker == "zerodha":
            return await self._sync_zerodha_instruments()
        return 0

    async def _sync_fyers_instruments(self) -> int:
        url = "https://public.fyers.in/sym_details/NSE_CM.csv"
        rows = []
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return 0
                for line in resp.text.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split(",")
                    if len(parts) < 15:
                        continue
                    fyers_symbol = parts[9].strip()
                    if not fyers_symbol:
                        continue
                    rows.append({
                        "symbol": parts[13].strip(),
                        "exchange": "NSE",
                        "broker": "fyers",
                        "broker_symbol": parts[13].strip(),
                        "token": parts[0].strip(),
                        "instrument_type": "EQ",
                        "lot_size": int(parts[3]) if parts[3].isdigit() else 1,
                        "tick_size": float(parts[4]) if parts[4].replace(".", "", 1).lstrip("-").isdigit() else 0.05,
                        "segment": "EQ",
                        "last_updated": date.today().isoformat(),
                    })
        except Exception as e:
            logger.warning("Fyers instrument sync failed: %s", e)
            return 0
        return await self._batch_upsert(rows)

    async def _sync_dhan_instruments(self) -> int:
        logger.warning("Dhan instrument sync not yet implemented")
        return 0

    async def _sync_zerodha_instruments(self) -> int:
        logger.warning("Zerodha instrument sync not yet implemented")
        return 0

    async def resolve_symbol(self, canonical: str, broker: str) -> str | None:
        supabase = get_supabase()
        try:
            result = await async_supabase(lambda: supabase.table("symbol_master").select("broker_symbol").eq("symbol", canonical).eq("broker", broker).maybe_single().execute())
            if result.data:
                return result.data["broker_symbol"]
        except Exception as e:
            logger.debug("Symbol resolution failed for %s/%s: %s", canonical, broker, e)
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
                count = await self.sync_fo_symbols()
                logger.info("Auto-synced %d F&O symbols", count)
                now = datetime.now(UTC)
                target = now.replace(hour=2, minute=30, second=0, microsecond=0)
                if now > target:
                    target = target + timedelta(days=1)
                delay = (target - now).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Auto-sync error: %s", e)
                await asyncio.sleep(3600)

    async def sync_fo_symbols(self) -> int:
        count = await self._sync_fyers_fo()
        if count > 0:
            return count
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://www.nseindia.com/api/fo-sec-list",
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                )
                if resp.status_code != 200:
                    return 0
                data = resp.json()
                rows = []
                for item in data:
                    symbol = item.get("symbol", "")
                    if not symbol:
                        continue
                    token = f"{symbol}-NFO"
                    rows.append({
                        "symbol": symbol,
                        "exchange": "NFO",
                        "broker": "master",
                        "broker_symbol": symbol,
                        "token": token,
                        "instrument_type": "FUT",
                        "lot_size": item.get("lotSize", 1),
                        "tick_size": 0.05,
                        "segment": "FO",
                        "last_updated": date.today().isoformat(),
                    })
                    self._fo_cache_put(symbol, {
                        "symbol": symbol,
                        "name": symbol,
                        "exchange": "NFO",
                        "instrument_type": "future",
                        "lot_size": item.get("lotSize", 1),
                    })
                count = await self._batch_upsert(rows)
                logger.info("Synced %d F&O symbols from NSE", count)
                return count
        except Exception as e:
            logger.warning("NSE F&O sync failed: %s", e)
            return 0

    async def _sync_fyers_fo(self) -> int:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                fo_resp = await client.get("https://public.fyers.in/sym_details/NSE_FO.csv")
                cm_resp = await client.get("https://public.fyers.in/sym_details/NSE_CM.csv")
        except Exception as e:
            logger.warning("Fyers CSV download failed: %s", e)
            return 0

        if fo_resp.status_code != 200 or cm_resp.status_code != 200:
            return 0

        fo_lines = fo_resp.text.splitlines()
        cm_lines = cm_resp.text.splitlines()

        futures_map: dict[str, dict] = {}
        db_rows: list[dict] = []

        for line in fo_lines:
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 21:
                continue
            fyers_symbol = parts[9].strip()
            if not fyers_symbol or not fyers_symbol.startswith("NSE:"):
                continue
            underlying = parts[13].strip()
            if not underlying:
                continue
            type_code = parts[2].strip()
            lot_size = int(parts[3]) if parts[3].isdigit() else 1
            tick_size = float(parts[4]) if parts[4].replace(".", "", 1).lstrip("-").isdigit() else 0.05

            if type_code == "11" and underlying not in futures_map:
                futures_map[underlying] = {
                    "symbol": underlying, "name": underlying,
                    "exchange": "NFO", "instrument_type": "future",
                    "lot_size": lot_size, "tick_size": tick_size,
                }
                db_rows.append({
                    "symbol": underlying,
                    "exchange": "NFO",
                    "broker": "fyers",
                    "broker_symbol": fyers_symbol,
                    "token": parts[0].strip(),
                    "instrument_type": "FUT",
                    "lot_size": lot_size,
                    "tick_size": tick_size,
                    "segment": "FO",
                    "last_updated": date.today().isoformat(),
                })

        for line in fo_lines:
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 21:
                continue
            fyers_symbol = parts[9].strip()
            if not fyers_symbol or not fyers_symbol.startswith("NSE:"):
                continue
            type_code = parts[2].strip()
            if type_code not in ("14", "15"):
                continue
            underlying = parts[13].strip()
            opt_type = parts[16].strip() if len(parts) > 16 else ""
            if opt_type not in ("CE", "PE"):
                continue
            strike = parts[15].strip() if len(parts) > 15 else ""
            if strike.endswith(".0"):
                strike = strike[:-2]
            lot_size = int(parts[3]) if parts[3].isdigit() else 1
            tick_size = float(parts[4]) if parts[4].replace(".", "", 1).lstrip("-").isdigit() else 0.05
            entry = {
                "symbol": fyers_symbol, "name": f"{underlying} {strike} {opt_type}",
                "exchange": "NFO", "instrument_type": "option",
                "lot_size": lot_size, "tick_size": tick_size,
                "strike": strike, "option_type": opt_type,
            }
            self._fo_cache_put(fyers_symbol, entry)

        for line in fo_lines:
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 21:
                continue
            fyers_symbol = parts[9].strip()
            if not fyers_symbol or not fyers_symbol.startswith("NSE:"):
                continue
            type_code = parts[2].strip()
            if type_code not in ("11", "13"):
                continue
            underlying = parts[13].strip()
            if underlying in futures_map:
                continue
            lot_size = int(parts[3]) if parts[3].isdigit() else 1
            tick_size = float(parts[4]) if parts[4].replace(".", "", 1).lstrip("-").isdigit() else 0.05
            futures_map[underlying] = {
                "symbol": underlying, "name": underlying,
                "exchange": "NFO", "instrument_type": "future",
                "lot_size": lot_size, "tick_size": tick_size,
            }

        for underlying, entry in futures_map.items():
            self._fo_cache_put(underlying, entry)

        equity_count = 0
        for line in cm_lines:
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 20:
                continue
            fyers_symbol = parts[9].strip()
            if not fyers_symbol or not fyers_symbol.startswith("NSE:"):
                continue
            symbol_name = parts[13].strip()
            if not symbol_name:
                continue
            active_flag = parts[19].strip()
            if active_flag != "1":
                continue
            if symbol_name in futures_map:
                continue
            self._fo_cache_put(symbol_name, {
                "symbol": symbol_name, "name": parts[1].strip(),
                "exchange": "NSE", "instrument_type": "EQ",
                "lot_size": 1, "tick_size": float(parts[4]) if parts[4].replace(".", "", 1).lstrip("-").isdigit() else 0.05,
            })
            equity_count += 1

        total_underlyings = len(futures_map)
        logger.info("Synced %d index F&O + %d equities from Fyers CSV", total_underlyings, equity_count)
        return total_underlyings or equity_count

    async def get_broker_symbol(self, canonical: str, broker: str) -> str | None:
        if broker == "master":
            return canonical
        cache_key = f"broker_symbol:{canonical}:{broker}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached.get("broker_symbol")
        result = await self.resolve_symbol(canonical, broker)
        if result:
            self._cache_put(cache_key, {"broker_symbol": result})
        return result

    def get_symbol_info(self, symbol: str) -> dict | None:
        info = self._fo_cache_get(symbol.upper())
        if info:
            return info
        return self._cache_get(symbol.upper())

    def search_symbols(self, query: str, instrument_type: str | None = None, limit: int = 20) -> list[dict]:
        q = query.upper().replace(" ", "")
        results = []
        seen = set()
        for sym, info in self._fo_cache.items():
            name = info.get("name", sym).upper().replace(" ", "")
            if q in sym or q in name:
                if instrument_type and info.get("instrument_type") != instrument_type:
                    continue
                dedup_key = info.get("symbol", sym)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                results.append(info)
                if len(results) >= limit:
                    break
        return results


symbol_master = SymbolMaster()

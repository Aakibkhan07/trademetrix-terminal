from datetime import date

import httpx

from core.db import get_supabase


class SymbolMaster:
    def __init__(self):
        self._cache: dict[str, dict] = {}

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
                supabase.table("symbol_master").upsert(row, on_conflict=["broker", "token"]).execute()
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
                supabase.table("symbol_master").upsert(row, on_conflict=["broker", "token"]).execute()
                count += 1
        return count

    async def _sync_dhan_instruments(self, supabase) -> int:
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        count = 0
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return 0
            lines = resp.text.strip().split("\n")
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) < 6:
                    continue
                row = {
                    "symbol": parts[2].strip(),
                    "exchange": parts[1].strip(),
                    "broker": "dhan",
                    "broker_symbol": parts[2].strip(),
                    "token": parts[0].strip(),
                    "instrument_type": parts[3].strip(),
                    "lot_size": int(parts[4]) if parts[4].isdigit() else 1,
                    "tick_size": 0.05,
                    "segment": parts[5].strip() if len(parts) > 5 else "EQ",
                    "last_updated": date.today().isoformat(),
                }
                supabase.table("symbol_master").upsert(row, on_conflict=["broker", "token"]).execute()
                count += 1
        return count

    async def _sync_zerodha_instruments(self, supabase) -> int:
        url = "https://api.kite.trade/instruments/NSE"
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
                    "symbol": parts[2].strip(),
                    "exchange": parts[0].strip(),
                    "broker": "zerodha",
                    "broker_symbol": f"{parts[2].strip()}:{parts[0].strip()}",
                    "token": parts[1].strip(),
                    "instrument_type": parts[5].strip(),
                    "lot_size": int(parts[6]) if parts[6].isdigit() else 1,
                    "tick_size": 0.05,
                    "segment": parts[4].strip(),
                    "last_updated": date.today().isoformat(),
                }
                supabase.table("symbol_master").upsert(row, on_conflict=["broker", "token"]).execute()
                count += 1
        return count

    async def resolve_symbol(self, canonical: str, broker: str) -> str | None:
        supabase = get_supabase()
        result = (
            supabase.table("symbol_master")
            .select("broker_symbol")
            .eq("symbol", canonical)
            .eq("broker", broker)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data["broker_symbol"]
        return canonical

    async def resolve_to_canonical(self, broker_symbol: str, broker: str) -> str | None:
        supabase = get_supabase()
        result = (
            supabase.table("symbol_master")
            .select("symbol")
            .eq("broker_symbol", broker_symbol)
            .eq("broker", broker)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data["symbol"]
        return broker_symbol


symbol_master = SymbolMaster()

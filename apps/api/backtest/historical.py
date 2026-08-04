"""Backtest historical data: durable candle store + gap-fill + continuous
futures + corporate action adjustment.

Reuses market.historical.historical_engine (Fyers → Yahoo) for live fetches;
persists everything into Supabase `candles` so long-range backtests work and
history accumulates across restarts. Write-through is best-effort (in-memory
fallback when the table is missing — same pattern as the builder).

Continuous futures: `NIFTY-CONT` stitches the monthly FUT contracts into one
proportional back-adjusted series (roll on the last trading day of the
contract month).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from core.db import async_supabase, get_supabase

logger = logging.getLogger(__name__)

_CACHE: dict[str, list[dict]] = {}
_CACHE_LIMIT = 64

MONTH_CODES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _interval_minutes(interval: str) -> int:
    interval = interval.lower().strip()
    try:
        if interval.endswith("min"):
            return int(interval.replace("min", ""))
        if interval.endswith("h"):
            return int(interval.replace("h", "")) * 60
        if interval.endswith("d"):
            return int(interval.replace("d", "")) * 1440
        if interval.endswith("m"):
            return int(interval.replace("m", ""))
        return int(interval)
    except (ValueError, AttributeError):
        return 15


def _ts_key(ts) -> str:
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def _normalize_ts(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts.astimezone(UTC)
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(UTC)


class BacktestHistoricalData:
    async def load(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: str = "15m",
        days: int = 60,
        start: str = "",
        end: str = "",
        user_id: str | None = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        """Durable candle load: Supabase-first, gap-fill from broker, upsert back."""
        start_dt, end_dt = self._resolve_range(days, start, end)
        cache_key = f"{exchange}:{symbol}:{interval}:{start_dt.date()}:{end_dt.date()}"
        if not force_refresh and cache_key in _CACHE:
            return _CACHE[cache_key]

        stored = await self._load_from_db(symbol, exchange, interval, start_dt, end_dt)
        candles = list(stored)

        if len(candles) < 2 or not self._covers_range(candles, start_dt, end_dt):
            fetched = await self._fetch_and_store(
                symbol=symbol, exchange=exchange, interval=interval,
                start_dt=start_dt, end_dt=end_dt, user_id=user_id,
            )
            if fetched:
                candles = self._merge_candles(candles, fetched)

        candles = self._trim_range(candles, start_dt, end_dt)
        candles.sort(key=lambda c: str(c.get("timestamp", "")))

        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[cache_key] = candles
        return candles

    async def _load_from_db(
        self, symbol: str, exchange: str, interval: str, start_dt: datetime, end_dt: datetime,
    ) -> list[dict]:
        try:
            supabase = get_supabase()
            result = await async_supabase(lambda: supabase.table("candles")
                                          .select("*")
                                          .eq("symbol", symbol)
                                          .eq("exchange", exchange)
                                          .eq("interval", interval)
                                          .gte("ts", start_dt.isoformat())
                                          .lte("ts", end_dt.isoformat())
                                          .order("ts", desc=False)
                                          .limit(50000)
                                          .execute())
            return [self._row_to_candle(r) for r in result.data or []]
        except Exception as e:
            logger.debug("Candle store read skipped: %s", e)
            return []

    async def _fetch_and_store(
        self, symbol: str, exchange: str, interval: str,
        start_dt: datetime, end_dt: datetime, user_id: str | None,
    ) -> list[dict]:
        from market.historical import historical_engine

        total_days = max(1, (end_dt - start_dt).days)
        candles = await historical_engine.get_historical(
            symbol=symbol, exchange=exchange, interval=interval,
            days=total_days, user_id=user_id,
        )
        if not candles:
            return []
        trimmed = [c for c in candles if self._in_range(c, start_dt, end_dt)]
        await self._store(trimmed, source="broker")
        return trimmed

    async def _store(self, candles: list[dict], source: str = "broker") -> None:
        if not candles:
            return
        try:
            supabase = get_supabase()
            rows = []
            for c in candles:
                ts = _normalize_ts(c.get("timestamp") or c.get("ts"))
                ts_iso = ts.isoformat()
                rows.append({
                    "id": f"{c.get('exchange', 'NSE')}:{c.get('symbol', '')}:{c.get('interval', '')}:{ts_iso}",
                    "symbol": c.get("symbol", ""),
                    "exchange": c.get("exchange", "NSE"),
                    "interval": c.get("interval", ""),
                    "ts": ts_iso,
                    "open": float(c.get("open", 0)),
                    "high": float(c.get("high", 0)),
                    "low": float(c.get("low", 0)),
                    "close": float(c.get("close", 0)),
                    "volume": int(float(c.get("volume", 0) or 0)),
                    "oi": int(float(c.get("oi", 0) or 0)),
                    "source": source,
                })
            for i in range(0, len(rows), 200):
                batch = rows[i:i + 200]
                await async_supabase(lambda b=batch: supabase.table("candles")
                                     .upsert(b, on_conflict="id").execute())
            logger.info("Stored %d candles to durable store", len(rows))
        except Exception as e:
            logger.warning("Candle store write skipped: %s", e)

    async def load_continuous(
        self,
        base_symbol: str,
        exchange: str = "NSE",
        interval: str = "1d",
        days: int = 365,
        start: str = "",
        end: str = "",
        user_id: str | None = None,
    ) -> list[dict]:
        """Stitch monthly FUT contracts into one proportional back-adjusted series.

        Contracts are named {BASE}{YY}{MON}FUT (e.g. NIFTY26AUGFUT). Roll on the
        last trading day of each contract month; earlier prices are scaled by the
        roll ratio close_old/close_new so the series is continuous.
        """
        base = str(base_symbol).upper().replace("-CONT", "")
        start_dt, end_dt = self._resolve_range(days, start, end)
        cache_key = f"CONT:{base}:{interval}:{start_dt.date()}:{end_dt.date()}"
        if cache_key in _CACHE:
            return _CACHE[cache_key]

        segments: list[list[dict]] = []
        month = start_dt.replace(day=1)
        while month <= end_dt:
            symbol = self._contract_symbol(base, month)
            if not symbol:
                month = self._next_month(month)
                continue
            seg = await self.load(
                symbol=f"{exchange}:{symbol}", exchange=exchange, interval=interval,
                days=max(40, (end_dt - start_dt).days), user_id=user_id,
            )
            if seg:
                segments.append(seg)
            month = self._next_month(month)

        continuous = self._stitch(segments, start_dt, end_dt)
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[cache_key] = continuous
        return continuous

    def _contract_symbol(self, base: str, month: datetime) -> str:
        from market.symbol_master import symbol_master
        yy = month.strftime("%y")
        code = MONTH_CODES[month.month - 1]
        symbol = f"{base}{yy}{code}FUT"
        info = symbol_master.get_symbol_info(f"NSE:{symbol}")
        if not info:
            info = symbol_master.get_symbol_info(symbol)
        return symbol if info else ""

    def _stitch(self, segments: list[list[dict]], start_dt: datetime, end_dt: datetime) -> list[dict]:
        if not segments:
            return []
        by_contract: list[tuple[datetime, list[dict]]] = []
        for seg in segments:
            if not seg:
                continue
            by_contract.append((_normalize_ts(seg[0].get("timestamp")), seg))
        by_contract.sort(key=lambda x: x[0])

        out: list[dict] = []
        adj = 1.0
        roll_dates: list[tuple[datetime, float]] = []

        for i, (_, seg) in enumerate(by_contract):
            if i == 0:
                for c in seg:
                    if _normalize_ts(c["timestamp"]) < start_dt:
                        continue
                    out.append(self._scaled(c, adj))
                prev_contract = seg
                continue

            prev = prev_contract[-1]
            roll_ts = _normalize_ts(prev["timestamp"])
            roll_close_new = float(seg[0].get("close", 0))
            roll_close_old = float(prev.get("close", 0))
            if roll_close_new > 0 and roll_close_old > 0:
                adj *= roll_close_old / roll_close_new
                roll_dates.append((roll_ts, adj))

            for c in seg:
                ts = _normalize_ts(c["timestamp"])
                if ts <= roll_ts:
                    continue
                out.append(self._scaled(c, adj))
            prev_contract = seg

        out.sort(key=lambda c: str(c.get("timestamp", "")))
        for r in out:
            r["continuous"] = True
        if out:
            out[-1]["roll_dates"] = [
                {"date": d.date().isoformat(), "adjustment": round(a, 6)} for d, a in roll_dates
            ]
        return self._trim_range(out, start_dt, end_dt)

    def _scaled(self, c: dict, adj: float) -> dict:
        d = dict(c)
        if adj != 1.0:
            for k in ("open", "high", "low", "close"):
                d[k] = round(float(d.get(k, 0)) * adj, 4)
        d["timestamp"] = _normalize_ts(d.get("timestamp", "")).isoformat()
        return d

    async def apply_corporate_actions(
        self, candles: list[dict], symbol: str,
    ) -> tuple[list[dict], list[dict]]:
        """Price-adjust candles before each action's ex-date (splits/bonuses).
        Returns (adjusted_candles, actions_applied). Fail-open: no actions → passthrough."""
        actions = await self._load_actions(symbol)
        if not actions:
            return candles, []

        adjusted = []
        applied: list[dict] = []
        for c in candles:
            ts = _normalize_ts(c.get("timestamp", ""))
            factor = 1.0
            for a in actions:
                ex_date = datetime.fromisoformat(str(a["ex_date"])).replace(tzinfo=UTC)
                if ts < ex_date:
                    factor *= self._action_factor(a)
            c = dict(c)
            if factor != 1.0:
                for k in ("open", "high", "low", "close"):
                    c[k] = round(float(c.get(k, 0)) / factor, 4)
            adjusted.append(c)

        applied = [
            {"symbol": a["symbol"], "action": a["action"], "ex_date": str(a["ex_date"]),
             "ratio": a.get("ratio", ""), "dividend_amount": float(a.get("dividend_amount", 0))}
            for a in actions
        ]
        return adjusted, applied

    def _action_factor(self, a: dict) -> float:
        action = str(a.get("action", "")).upper()
        if action in ("SPLIT", "BONUS"):
            ratio = str(a.get("ratio", "") or "")
            try:
                if ":" in ratio:
                    old, new = ratio.split(":")
                    return float(new) / float(old)
            except (ValueError, ZeroDivisionError):
                pass
        return 1.0

    async def _load_actions(self, symbol: str) -> list[dict]:
        try:
            supabase = get_supabase()
            result = await async_supabase(lambda: supabase.table("corporate_actions")
                                          .select("*").eq("symbol", symbol.upper())
                                          .order("ex_date", desc=False).execute())
            return result.data or []
        except Exception as e:
            logger.debug("Corporate actions read skipped: %s", e)
            return []

    # ─── helpers ───

    def _resolve_range(self, days: int, start: str, end: str) -> tuple[datetime, datetime]:
        end_dt = datetime.now(UTC)
        if end:
            try:
                end_dt = _normalize_ts(end)
            except (ValueError, TypeError):
                pass
        start_dt = end_dt - timedelta(days=max(1, days))
        if start:
            try:
                start_dt = _normalize_ts(start)
            except (ValueError, TypeError):
                pass
        return start_dt, end_dt

    def _in_range(self, c: dict, start_dt: datetime, end_dt: datetime) -> bool:
        try:
            ts = _normalize_ts(c.get("timestamp") or c.get("ts"))
            return start_dt - timedelta(minutes=_interval_minutes(str(c.get("interval", "15m")))) <= ts <= end_dt + timedelta(minutes=_interval_minutes(str(c.get("interval", "15m"))))
        except (ValueError, TypeError):
            return False

    def _trim_range(self, candles: list[dict], start_dt: datetime, end_dt: datetime) -> list[dict]:
        margin = timedelta(minutes=_interval_minutes(str(candles[0].get("interval", "15m"))) if candles else 15)
        return [c for c in candles if self._in_range(c, start_dt - margin, end_dt + margin)]

    def _covers_range(self, candles: list[dict], start_dt: datetime, end_dt: datetime) -> bool:
        """True when the stored slice covers the full requested window.

        Trading-day tolerance: intraday candles only exist between ~09:15–15:30
        IST, so edge candles can legitimately sit up to ~1 day inside the
        requested boundary.
        """
        if not candles:
            return False
        try:
            first = _normalize_ts(candles[0].get("timestamp") or candles[0].get("ts"))
            last = _normalize_ts(candles[-1].get("timestamp") or candles[-1].get("ts"))
        except (ValueError, TypeError, KeyError):
            return False
        tolerance = timedelta(days=1)
        return first <= start_dt + tolerance and last >= end_dt - tolerance

    def _merge_candles(self, stored: list[dict], fetched: list[dict]) -> list[dict]:
        """Union stored + fetched candles by timestamp, preferring fetched on conflicts."""
        by_ts: dict[str, dict] = {}
        for c in stored:
            ts = _normalize_ts(c.get("timestamp") or c.get("ts"))
            by_ts.setdefault(ts.isoformat(), c)
        for c in fetched:
            ts = _normalize_ts(c.get("timestamp") or c.get("ts"))
            by_ts[ts.isoformat()] = c
        return sorted(by_ts.values(), key=lambda c: str(c.get("timestamp", "")))

    def _next_month(self, d: datetime) -> datetime:
        if d.month == 12:
            return d.replace(year=d.year + 1, month=1)
        return d.replace(month=d.month + 1)

    def _row_to_candle(self, r: dict) -> dict:
        return {
            "symbol": r.get("symbol", ""),
            "exchange": r.get("exchange", "NSE"),
            "interval": r.get("interval", ""),
            "open": float(r.get("open", 0)),
            "high": float(r.get("high", 0)),
            "low": float(r.get("low", 0)),
            "close": float(r.get("close", 0)),
            "volume": int(r.get("volume", 0) or 0),
            "timestamp": _ts_key(r.get("ts")),
            "oi": int(r.get("oi", 0) or 0),
            "source": r.get("source", "db"),
        }


backtest_historical = BacktestHistoricalData()

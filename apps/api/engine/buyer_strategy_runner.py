"""BuyerStrategyRunner — standalone runner for options-buying strategies.

Subscribes to underlying index ticks, aggregates 5-min candles, and feeds
them to strategy instances. Each active strategy runs in its own asyncio.Task.
State is stored in-memory with Redis as secondary (for restart recovery).
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from core.cache import cache
from core.config import settings
from core.models import Tick
from market.candle_aggregator import CandleAggregator
from market.data_socket import shared_socket
from strategies import get_strategy

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

BUYER_KEYS = frozenset({"momentum_breakout_buyer", "trend_rider_buyer", "long_straddle"})
CACHE_ACTIVE_KEY = "buyer_runner:active"
CACHE_CONFIG_PREFIX = "buyer_runner:config:"
CACHE_INDEX_PREFIX = "buyer_runner:index:"
POLL_INTERVAL = 30
CANDLE_INTERVAL = "5m"

DEFAULT_USER_ID = settings.default_buyer_user_id

AUTO_CONFIGS: dict[str, dict] = {
    "B1-momentum": {
        "strategy_id": "B1-momentum",
        "strategy_key": "momentum_breakout_buyer",
        "user_id": DEFAULT_USER_ID,
        "index": "NIFTY",
        "backtest_mode": True,
        "capital": 50000.0,
        "risk_per_trade_pct": 1.0,
        "max_outlay_pct": 10.0,
        "sl_pct": 10.0,
        "rr_target": 1.5,
        "itm_offset_steps": 0,
        "vol_mult": 1.5,
        "time_stop_min": 30,
    },
    "B2-trend-rider": {
        "strategy_id": "B2-trend-rider",
        "strategy_key": "trend_rider_buyer",
        "user_id": DEFAULT_USER_ID,
        "index": "NIFTY",
        "backtest_mode": True,
        "capital": 50000.0,
        "risk_per_trade_pct": 1.0,
        "max_outlay_pct": 10.0,
        "sl_pct": 10.0,
        "rr_target": 1.5,
        "itm_offset_steps": 0,
        "time_stop_min": 40,
    },
    "B3-straddle": {
        "strategy_id": "B3-straddle",
        "strategy_key": "long_straddle",
        "user_id": DEFAULT_USER_ID,
        "index": "NIFTY",
        "backtest_mode": True,
        "capital": 50000.0,
        "risk_per_trade_pct": 1.0,
        "max_outlay_pct": 10.0,
        "itm_offset_steps": 0,
        "time_stop_min": 45,
        "combined_loss_pct": 10,
        "leg_target_multiple": 1.2,
    },
}


class BuyerStrategyRunner:
    def __init__(self):
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._tasks: dict[str, asyncio.Task] = {}
        self._bg_tasks: set[asyncio.Task] = set()
        self._active: list[str] = []
        self._configs: dict[str, dict] = {}
        self._indices: dict[str, str] = {}
        self._auto_activated_today: bool = False
        self._auto_today_str: str = ""

    async def start(self):
        if self._running:
            return
        self._running = True
        await self._rehydrate()
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("BuyerStrategyRunner started with %d active strategies", len(self._active))

    async def stop(self):
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        for sid in list(self._tasks.keys()):
            await self._cancel_task(sid)
        self._active.clear()
        self._configs.clear()
        self._indices.clear()
        logger.info("BuyerStrategyRunner stopped")

    async def _rehydrate(self):
        active = await cache.get(CACHE_ACTIVE_KEY, [])
        if isinstance(active, list):
            for sid in active:
                cfg = await cache.get(f"{CACHE_CONFIG_PREFIX}{sid}")
                idx = await cache.get(f"{CACHE_INDEX_PREFIX}{sid}", "NIFTY")
                if cfg:
                    self._active.append(sid)
                    self._configs[sid] = cfg
                    self._indices[sid] = idx
        if self._active:
            logger.info("Rehydrated %d buyer strategies from cache", len(self._active))

    def _bg(self, coro):
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _persist_active(self):
        self._bg(cache.set(CACHE_ACTIVE_KEY, self._active, ttl=86400))

    def _persist_config(self, sid: str):
        cfg = self._configs.get(sid)
        idx = self._indices.get(sid, "NIFTY")
        if cfg:
            self._bg(cache.set(f"{CACHE_CONFIG_PREFIX}{sid}", cfg, ttl=86400))
            self._bg(cache.set(f"{CACHE_INDEX_PREFIX}{sid}", idx, ttl=86400))

    def _remove_config(self, sid: str):
        self._bg(cache.delete(f"{CACHE_CONFIG_PREFIX}{sid}"))
        self._bg(cache.delete(f"{CACHE_INDEX_PREFIX}{sid}"))

    async def _auto_activate(self):
        logger.info("Market open — auto-activating all buyer strategies")
        for sid, cfg in AUTO_CONFIGS.items():
            index = cfg.get("index", "NIFTY")
            await self.activate(sid, cfg, index)
        self._auto_activated_today = True
        logger.info("Auto-activated %d buyer strategies", len(AUTO_CONFIGS))

    async def _run_loop(self):
        while self._running:
            try:
                await self._sync()
            except Exception:
                logger.exception("BuyerStrategyRunner sync error")
            await asyncio.sleep(POLL_INTERVAL)

    async def _sync(self):
        now = datetime.now(IST)
        market_open = now.hour * 60 + now.minute >= 9 * 60 + 15
        market_close = now.hour * 60 + now.minute > 15 * 60 + 30
        today = now.strftime("%Y%m%d")

        # Reset auto-activate flag on new day or after market close
        if today != self._auto_today_str:
            self._auto_activated_today = False
            self._auto_today_str = today
        if market_close:
            self._auto_activated_today = True

        # Auto-activate all 3 strategies when market opens (once per day)
        if market_open and not self._auto_activated_today and not self._active:
            await self._auto_activate()

        for sid in list(self._active):
            if sid in self._tasks and not self._tasks[sid].done():
                continue
            if market_close:
                continue
            if not market_open:
                continue
            cfg = self._configs.get(sid)
            if not cfg:
                continue
            idx = self._indices.get(sid, "NIFTY")
            task = asyncio.create_task(self._feed_loop(sid, cfg, idx))
            self._tasks[sid] = task
            logger.info("Started buyer strategy: %s (%s)", sid, cfg.get("strategy_key", "?"))

        for sid in list(self._tasks.keys()):
            if sid not in self._active:
                await self._cancel_task(sid)

    async def activate(self, strategy_id: str, config: dict, index: str = "NIFTY") -> bool:
        if strategy_id not in self._active:
            self._active.append(strategy_id)
        self._configs[strategy_id] = config
        self._indices[strategy_id] = index
        self._persist_active()
        self._persist_config(strategy_id)
        logger.info("Buyer strategy activated: %s key=%s index=%s", strategy_id, config.get("strategy_key"), index)
        return True

    async def deactivate(self, strategy_id: str) -> bool:
        if strategy_id in self._active:
            self._active.remove(strategy_id)
        self._configs.pop(strategy_id, None)
        self._indices.pop(strategy_id, None)
        await self._cancel_task(strategy_id)
        self._persist_active()
        self._remove_config(strategy_id)
        logger.info("Buyer strategy deactivated: %s", strategy_id)
        return True

    async def get_statuses(self) -> list[dict]:
        result = []
        for sid in self._active:
            cfg = self._configs.get(sid, {})
            idx = self._indices.get(sid, "")
            running = sid in self._tasks and not self._tasks[sid].done()
            result.append({
                "strategy_id": sid,
                "strategy_key": cfg.get("strategy_key", ""),
                "index": idx,
                "running": running,
                "config": cfg,
            })
        return result

    async def _cancel_task(self, sid: str):
        task = self._tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _feed_loop(self, strategy_id: str, config: dict, index_symbol: str):
        tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=500)
        stop_event = asyncio.Event()

        strategy_key = config.get("strategy_key", "")
        try:
            cls = get_strategy(strategy_key)
        except ValueError:
            logger.error("Unknown strategy key: %s", strategy_key)
            return

        instance = cls(config)
        try:
            await instance.on_start()
        except Exception as e:
            logger.error("on_start failed for %s: %s", strategy_id, e)
            return

        aggregator = CandleAggregator(index_symbol, CANDLE_INTERVAL)
        live_feed_active = False

        dropped_ticks = 0

        async def tick_handler(tick: Tick) -> None:
            nonlocal dropped_ticks
            if tick.symbol == index_symbol or tick.symbol.endswith(f":{index_symbol}"):
                try:
                    await asyncio.wait_for(tick_queue.put(tick), timeout=1)
                except asyncio.QueueFull:
                    dropped_ticks += 1
                    if dropped_ticks == 1 or dropped_ticks % 100 == 0:
                        logger.warning("Tick queue full for %s — dropped %d ticks", strategy_id, dropped_ticks)
                except asyncio.TimeoutError:
                    dropped_ticks += 1

        shared_socket.subscribe(index_symbol, tick_handler)
        shared_socket.subscribe("*", tick_handler)
        logger.info("Buyer runner subscribed to %s for %s", index_symbol, strategy_id)

        try:
            while not stop_event.is_set():
                try:
                    tick = await asyncio.wait_for(tick_queue.get(), timeout=30)
                    live_feed_active = True
                    candle = aggregator.add_tick(tick)
                    if candle:
                        try:
                            await instance.on_candle(candle)
                        except Exception as e:
                            logger.error("on_candle error %s: %s", strategy_id, e)
                except asyncio.TimeoutError:
                    if live_feed_active:
                        continue
                    logger.debug("Waiting for first tick for %s", strategy_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("Buyer feed loop error for %s: %s", strategy_id, e)
        finally:
            shared_socket.unsubscribe(index_symbol, tick_handler)
            shared_socket.unsubscribe("*", tick_handler)
            try:
                await instance.on_stop()
            except Exception as e:
                logger.warning("on_stop error %s: %s", strategy_id, e)
            logger.info("Buyer feed loop ended for %s", strategy_id)


buyer_strategy_runner = BuyerStrategyRunner()

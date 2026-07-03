import asyncio
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any

from core.models import Candle, Tick
from runtime.models import TriggerType

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class RuntimeScheduler:
    def __init__(self):
        self._triggers: dict[str, dict] = {}
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._minute_task: asyncio.Task | None = None
        self._market_tasks: dict[str, asyncio.Task] = {}

    def register(self, strategy_id: str, trigger: TriggerType, callback: Any, interval: str = "1m", cron: str = "") -> None:
        self._triggers[strategy_id] = {
            "trigger": trigger,
            "callback": callback,
            "interval": interval,
            "cron": cron,
            "active": False,
            "last_run": None,
        }
        logger.info("Scheduler registered %s with trigger %s", strategy_id, trigger)

    def unregister(self, strategy_id: str) -> None:
        self._triggers.pop(strategy_id, None)

    async def start(self) -> None:
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        self._minute_task = asyncio.create_task(self._minute_loop())
        logger.info("RuntimeScheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
        if self._minute_task:
            self._minute_task.cancel()
        for task in self._market_tasks.values():
            task.cancel()
        self._market_tasks.clear()
        logger.info("RuntimeScheduler stopped")

    async def on_tick(self, tick: Tick) -> None:
        for sid, config in list(self._triggers.items()):
            if config["trigger"] in (TriggerType.EVERY_TICK,) and config["active"]:
                try:
                    result = config["callback"](tick=tick)
                    if hasattr(result, "__await__"):
                        await result
                except Exception as e:
                    logger.error("Tick callback error for %s: %s", sid, e)

    async def on_candle(self, candle: Candle) -> None:
        for sid, config in list(self._triggers.items()):
            if config["trigger"] in (TriggerType.CANDLE_CLOSE,) and config["active"]:
                interval_match = not config["interval"] or config["interval"] == candle.interval
                if interval_match:
                    try:
                        result = config["callback"](candle=candle)
                        if hasattr(result, "__await__"):
                            await result
                    except Exception as e:
                        logger.error("Candle callback error for %s: %s", sid, e)

    async def _run_loop(self):
        while self._running:
            now = datetime.now(IST)
            current_minute = now.hour * 60 + now.minute
            market_open = 9 * 60 + 15
            market_close = 15 * 60 + 30

            for sid, config in list(self._triggers.items()):
                trigger = config["trigger"]

                if trigger == TriggerType.MARKET_OPEN:
                    if current_minute == market_open and not config["active"]:
                        config["active"] = True
                        asyncio.create_task(self._run_callback(sid, config))
                elif trigger == TriggerType.MARKET_CLOSE:
                    if current_minute == market_close and not config["active"]:
                        config["active"] = True
                        asyncio.create_task(self._run_callback(sid, config))
                elif trigger == TriggerType.CRON:
                    if self._cron_matches(config["cron"], now) and not config["active"]:
                        config["active"] = True
                        asyncio.create_task(self._run_callback(sid, config))

                if trigger in (TriggerType.MARKET_OPEN, TriggerType.MARKET_CLOSE, TriggerType.CRON):
                    if config["active"]:
                        config["last_run"] = now

            await asyncio.sleep(30)

    async def _minute_loop(self):
        while self._running:
            now = datetime.now(IST)
            for sid, config in list(self._triggers.items()):
                trigger = config["trigger"]

                if trigger == TriggerType.EVERY_MINUTE:
                    if config["active"]:
                        asyncio.create_task(self._run_callback(sid, config))
                elif trigger == TriggerType.EVERY_5_MINUTES:
                    if config["active"] and now.minute % 5 == 0:
                        asyncio.create_task(self._run_callback(sid, config))

            await asyncio.sleep(60)

    async def _run_callback(self, sid: str, config: dict) -> None:
        try:
            result = config["callback"]()
            if hasattr(result, "__await__"):
                await result
        except Exception as e:
            logger.error("Callback error for %s: %s", sid, e)
        finally:
            config["active"] = False
            config["last_run"] = datetime.now(IST)

    @staticmethod
    def _cron_matches(expression: str, dt: datetime) -> bool:
        if not expression:
            return False
        parts = expression.strip().split()
        if len(parts) < 5:
            return False
        minute_pattern = parts[0]
        hour_pattern = parts[1]
        if (minute_pattern == "*" or int(minute_pattern) == dt.minute) and \
           (hour_pattern == "*" or int(hour_pattern) == dt.hour):
            return True
        return False


scheduler = RuntimeScheduler()

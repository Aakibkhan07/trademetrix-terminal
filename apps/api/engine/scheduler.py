import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class ISTScheduler:
    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._running = False
        self._loop_task: asyncio.Task | None = None

    def add_strategy(
        self,
        strategy_id: str,
        callback: Callable,
        start_time: time,
        end_time: time,
        days_of_week: list[int] | None = None,
    ):
        self._tasks[strategy_id] = {
            "callback": callback,
            "start_time": start_time,
            "end_time": end_time,
            "days_of_week": days_of_week or [0, 1, 2, 3, 4],
            "active": False,
        }

    def remove_strategy(self, strategy_id: str):
        self._tasks.pop(strategy_id, None)

    async def start(self):
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("ISTScheduler started")

    async def stop(self):
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("ISTScheduler stopped")

    async def _run_loop(self):
        while self._running:
            now = datetime.now(IST)
            current_time = now.time()
            current_dow = now.weekday()

            for strategy_id, config in self._tasks.items():
                should_run = (
                    current_dow in config["days_of_week"]
                    and config["start_time"] <= current_time <= config["end_time"]
                    and now.isoweekday() <= 5
                )

                if should_run and not config["active"]:
                    config["active"] = True
                    asyncio.create_task(self._run_strategy(strategy_id, config))
                    logger.info(f"Strategy {strategy_id} activated")

                elif not should_run and config["active"]:
                    config["active"] = False
                    logger.info(f"Strategy {strategy_id} deactivated")

            await asyncio.sleep(30)

    async def _run_strategy(self, strategy_id: str, config: dict):
        try:
            await config["callback"]()
        except Exception as e:
            logger.error(f"Strategy {strategy_id} error: {e}", exc_info=True)
        finally:
            config["active"] = False

    async def square_off_all(self, executor_getter: Callable):
        market_close = time(15, 30)
        square_off_time = time(15, 15)

        while self._running:
            current = datetime.now(IST).time()
            if square_off_time <= current <= market_close:
                for strategy_id in list(self._tasks.keys()):
                    executor = executor_getter(strategy_id)
                    if executor:
                        positions = await executor.get_positions()
                        for pos in positions:
                            if pos.quantity != 0:
                                side = "SELL" if pos.quantity > 0 else "BUY"
                                logger.info(f"Square off: {pos.symbol} {side}")
            await asyncio.sleep(60)


scheduler = ISTScheduler()

import asyncio
import logging
import time
from datetime import UTC, datetime

from backtest.models import ReplaySpeed, SPEED_MULTIPLIERS
from core.models import Candle, Exchange, NormalizedOrder
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest
from portfolio.manager import portfolio_manager
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class ReplayEngine:
    def __init__(self):
        self._paused = asyncio.Event()
        self._paused.set()
        self._stopped = False
        self._current_index = 0
        self._total_candles = 0
        self._current_speed: ReplaySpeed = ReplaySpeed.MAX
        self._start_time = 0.0
        self._bt_user_id = ""
        self._current_candle: Candle | None = None

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()

    @property
    def is_running(self) -> bool:
        return self._start_time > 0 and not self._stopped

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def progress_pct(self) -> float:
        if self._total_candles == 0:
            return 0.0
        return round(self._current_index / self._total_candles * 100, 1)

    def configure(self, bt_user_id: str, speed: ReplaySpeed = ReplaySpeed.MAX):
        self._bt_user_id = bt_user_id
        self._current_speed = speed

    async def run(
        self,
        strategy: BaseStrategy,
        raw_candles: list[dict],
        exec_mgr: ExecutionManager,
        snapshots: list[dict],
        buffer_interval_s: float = 0.0,
    ) -> None:
        self._stopped = False
        self._total_candles = len(raw_candles)
        self._current_index = 0
        self._start_time = time.monotonic()

        await self._prefetch_positions()

        try:
            for idx, raw in enumerate(raw_candles):
                if self._stopped:
                    break

                await self._paused.wait()

                self._current_index = idx
                candle = self._dict_to_candle(raw)
                self._current_candle = candle

                try:
                    signal = await strategy.on_candle(candle)

                    if signal and signal.orders:
                        for order in signal.orders:
                            req = self._order_to_request(order)
                            result = await exec_mgr.place_order(req)
                            if not result.success:
                                logger.debug(
                                    "Order failed at candle %d: %s - %s",
                                    idx, order.symbol, result.message,
                                )
                except Exception as e:
                    logger.error("Candle %d evaluation error: %s", idx, e)

                snapshot = await self._collect_snapshot()
                snapshots.append(snapshot)

                await self._apply_speed_delay(raw, idx)

                # yield control every 100 candles
                if idx > 0 and idx % 100 == 0:
                    await asyncio.sleep(0)

        except asyncio.CancelledError:
            logger.info("ReplayEngine cancelled at candle %d/%d", self._current_index, self._total_candles)
            raise

    async def pause(self):
        self._paused.clear()
        logger.info("ReplayEngine paused at candle %d/%d", self._current_index, self._total_candles)

    async def resume(self):
        self._paused.set()
        logger.info("ReplayEngine resumed at candle %d/%d", self._current_index, self._total_candles)

    async def stop(self):
        self._stopped = True
        self._paused.set()
        logger.info("ReplayEngine stopped at candle %d/%d", self._current_index, self._total_candles)

    def set_speed(self, speed: ReplaySpeed):
        self._current_speed = speed
        logger.info("ReplayEngine speed set to %s", speed)

    async def seek(self, target_index: int, raw_candles: list[dict]) -> list[dict]:
        target_index = max(0, min(target_index, len(raw_candles) - 1))
        self._current_index = target_index
        candle = self._dict_to_candle(raw_candles[target_index])
        self._current_candle = candle
        logger.info("ReplayEngine seeked to candle %d/%d", target_index, len(raw_candles))
        return [raw_candles[target_index]]

    async def _prefetch_positions(self):
        try:
            await portfolio_manager.get_portfolio(self._bt_user_id, "paper")
        except Exception as e:
            logger.warning("Replay engine portfolio init failed: %s", e)

    async def _collect_snapshot(self) -> dict:
        snapshot = {
            "index": self._current_index,
            "timestamp": str(datetime.now(UTC)),
            "equity": 0.0,
            "positions": [],
            "pnl": {},
        }
        try:
            portfolio = await portfolio_manager.get_portfolio(self._bt_user_id, "paper")
            snapshot["equity"] = portfolio.pnl.current_equity if portfolio.pnl else 0.0
            snapshot["positions"] = [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "unrealised_pnl": p.unrealised_pnl,
                    "realised_pnl": p.realised_pnl,
                    "average_buy_price": p.average_buy_price,
                }
                for p in portfolio.positions.values()
            ]
            if portfolio.pnl:
                snapshot["pnl"] = {
                    "realised": portfolio.pnl.realised_pnl,
                    "unrealised": portfolio.pnl.unrealised_pnl,
                    "daily": portfolio.pnl.daily_pnl,
                    "overall": portfolio.pnl.overall_pnl,
                }
        except Exception as e:
            logger.debug("Snapshot collection error: %s", e)
        return snapshot

    async def _apply_speed_delay(self, raw: dict, idx: int):
        multiplier = SPEED_MULTIPLIERS.get(self._current_speed, 0.0)
        if multiplier <= 0:
            return

        if idx < self._total_candles - 1:
            interval_min = self._parse_interval(raw.get("interval", "15m"))
            delay = (interval_min * 60) / multiplier
            if delay > 0:
                await asyncio.sleep(delay)

    def _parse_interval(self, interval: str) -> int:
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
            if interval.endswith("s"):
                return max(1, int(interval.replace("s", "")) // 60)
            return int(interval)
        except (ValueError, AttributeError):
            return 15

    def _dict_to_candle(self, d: dict) -> Candle:
        exchange_name = d.get("exchange", "NSE")
        exchange = Exchange(exchange_name) if isinstance(exchange_name, str) else exchange_name
        ts = d.get("timestamp", "")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, (int, float)):
            ts = datetime.utcfromtimestamp(ts)
        return Candle(
            symbol=d.get("symbol", ""),
            exchange=exchange,
            interval=d.get("interval", ""),
            open=float(d.get("open", 0)),
            high=float(d.get("high", 0)),
            low=float(d.get("low", 0)),
            close=float(d.get("close", 0)),
            volume=int(float(d.get("volume", 0))),
            timestamp=ts,
            oi=int(float(d.get("oi", 0))),
        )

    def _order_to_request(self, order: NormalizedOrder) -> ExecutionRequest:
        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        return ExecutionRequest(
            user_id=self._bt_user_id,
            broker="paper",
            symbol=order.symbol,
            exchange=order.exchange.value if hasattr(order.exchange, "value") else "NSE",
            side=side,
            order_type=order.order_type.value if hasattr(order.order_type, "value") else "MARKET",
            product=order.product.value if hasattr(order.product, "value") else "INTRADAY",
            quantity=order.quantity,
            price=order.price,
            trigger_price=order.trigger_price,
            strategy_id=order.strategy_id,
            source="backtest",
        )


replay_engine = ReplayEngine()

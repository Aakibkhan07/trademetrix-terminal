import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class BacktestStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReplaySpeed(StrEnum):
    ONE_X = "1x"
    TWO_X = "2x"
    FIVE_X = "5x"
    TEN_X = "10x"
    HUNDRED_X = "100x"
    MAX = "MAX"


SPEED_MULTIPLIERS: dict[ReplaySpeed, float] = {
    ReplaySpeed.ONE_X: 1.0,
    ReplaySpeed.TWO_X: 2.0,
    ReplaySpeed.FIVE_X: 5.0,
    ReplaySpeed.TEN_X: 10.0,
    ReplaySpeed.HUNDRED_X: 100.0,
    ReplaySpeed.MAX: 0.0,
}


class BacktestConfig(BaseModel):
    strategy_type: str
    strategy_params: dict = Field(default_factory=dict)
    symbol: str = "NIFTY"
    exchange: str = "NSE"
    interval: str = "15m"
    days: int = 60
    initial_capital: float = 100000.0
    speed: ReplaySpeed = ReplaySpeed.MAX
    data_source: str = "auto"
    file_path: str = ""
    risk_enabled: bool = True
    close_positions_on_end: bool = True


class CandleSnapshot(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class TradeRecord(BaseModel):
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    entry_time: str
    exit_time: str
    duration_minutes: int = 0
    exit_reason: str = "signal"


class EquityPoint(BaseModel):
    timestamp: str
    equity: float
    drawdown: float = 0.0
    drawdown_pct: float = 0.0


class BacktestResult(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str = ""
    status: BacktestStatus = BacktestStatus.IDLE
    config: BacktestConfig = Field(default_factory=BacktestConfig)

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    net_pnl: float = 0.0

    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    total_fees: float = 0.0
    average_trade_duration_minutes: float = 0.0
    candles_analyzed: int = 0
    start_equity: float = 0.0
    end_equity: float = 0.0
    return_pct: float = 0.0

    trades: list[TradeRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    monthly_returns: dict[str, float] = Field(default_factory=dict)
    daily_returns: dict[str, float] = Field(default_factory=dict)

    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    error: str = ""

"""Indian market cost model for backtests.

Computes realistic per-trade charges for NSE cash, futures and options:
slippage, brokerage, exchange transaction charges, STT, stamp duty, GST and
SEBI fees. All rates are configurable via BacktestCostConfig with current
NSE/SEBI defaults. Pure functions — no I/O, no state.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CostSegment(StrEnum):
    EQUITY_DELIVERY = "equity_delivery"
    EQUITY_INTRADAY = "equity_intraday"
    FUTURES = "futures"
    OPTIONS = "options"


class BacktestCostConfig(BaseModel):
    """Cost knobs. All percentages are per unit of traded value (not per lot)."""

    slippage_pct: float = 0.05          # applied to fill price, both sides
    commission_pct: float = 0.03        # brokerage override knob (0.03% of value)
    commission_min: float = 20.0        # minimum brokerage per order (₹)
    brokerage_flat_options: float = 20.0  # flat brokerage per options order (₹)
    stt_enabled: bool = True
    exchange_charges_enabled: bool = True
    stamp_duty_enabled: bool = True
    gst_enabled: bool = True
    sebi_fees_enabled: bool = True
    gst_rate: float = 18.0              # % on (brokerage + exchange charges)
    sebi_fees_per_crore: float = 10.0   # ₹ per ₹1 crore traded value


# NSE transaction charges (% of traded value) — current rates
EXCHANGE_TC_RATES: dict[CostSegment, float] = {
    CostSegment.EQUITY_DELIVERY: 0.00297,
    CostSegment.EQUITY_INTRADAY: 0.00297,
    CostSegment.FUTURES: 0.00173,
    CostSegment.OPTIONS: 0.03503,
}

# Securities Transaction Tax (% of traded value) — current rates
STT_RATES: dict[CostSegment, float] = {
    CostSegment.EQUITY_DELIVERY: 0.1,   # sell side only
    CostSegment.EQUITY_INTRADAY: 0.025, # both sides
    CostSegment.FUTURES: 0.0125,        # sell side only
    CostSegment.OPTIONS: 0.1,           # sell side, on premium value
}

# Stamp duty (% of traded value, buy side only) — current rates
STAMP_DUTY_RATES: dict[CostSegment, float] = {
    CostSegment.EQUITY_DELIVERY: 0.015,
    CostSegment.EQUITY_INTRADAY: 0.003,
    CostSegment.FUTURES: 0.002,
    CostSegment.OPTIONS: 0.003,
}

CRORE = 100_000_000


def segment_for(instrument_type: str, product: str | None = None) -> CostSegment:
    """Map an instrument to the cost segment.

    instrument_type: EQ | FUT | OPT (matches core.models.InstrumentType)
    product: INTRADAY | DELIVERY | MARGIN (delivery != INTRADAY → delivery)
    """
    it = str(instrument_type or "").upper()
    if it in ("FUT", "FUTURE", "FUTURES"):
        return CostSegment.FUTURES
    if it in ("OPT", "OPTION", "OPTIONS", "CE", "PE"):
        return CostSegment.OPTIONS
    product = str(product or "").upper()
    if product == "DELIVERY":
        return CostSegment.EQUITY_DELIVERY
    return CostSegment.EQUITY_INTRADAY


class CostEstimate(BaseModel):
    segment: str
    traded_value: float
    slippage: float = 0.0
    brokerage: float = 0.0
    exchange_tc: float = 0.0
    stt: float = 0.0
    stamp_duty: float = 0.0
    gst: float = 0.0
    sebi: float = 0.0
    total: float = 0.0


def estimate_cost(
    side: str,
    traded_value: float,
    segment: CostSegment | str,
    qty: float = 0.0,
    price: float = 0.0,
    slippage_value: float = 0.0,
    config: BacktestCostConfig | None = None,
) -> CostEstimate:
    """Compute all charges for one fill.

    side: BUY | SELL
    traded_value: qty * fill_price (after slippage)
    slippage_value: monetary slippage already applied to the price (qty * Δprice)
    """
    seg = segment if isinstance(segment, CostSegment) else CostSegment(segment)
    cfg = config or BacktestCostConfig()
    side = str(side or "").upper()

    slippage = round(abs(slippage_value), 2)

    # ── Brokerage ──
    if seg == CostSegment.OPTIONS:
        brokerage = round(cfg.brokerage_flat_options, 2)
    else:
        brokerage = round(max(traded_value * cfg.commission_pct / 100, cfg.commission_min), 2)

    # ── Exchange transaction charges ──
    exchange_tc = round(traded_value * EXCHANGE_TC_RATES[seg] / 100, 2) if cfg.exchange_charges_enabled else 0.0

    # ── STT ──
    stt = 0.0
    if cfg.stt_enabled:
        rate = STT_RATES[seg]
        if seg == CostSegment.EQUITY_DELIVERY and side == "BUY":
            rate = 0.0
        elif seg == CostSegment.FUTURES and side == "BUY":
            rate = 0.0
        elif seg == CostSegment.OPTIONS and side == "BUY":
            rate = 0.0
        stt = round(traded_value * rate / 100, 2)

    # ── Stamp duty (buy side only) ──
    stamp_duty = 0.0
    if cfg.stamp_duty_enabled and side == "BUY":
        stamp_duty = round(traded_value * STAMP_DUTY_RATES[seg] / 100, 2)

    # ── GST on (brokerage + exchange charges) ──
    gst = 0.0
    if cfg.gst_enabled:
        gst = round((brokerage + exchange_tc) * cfg.gst_rate / 100, 2)

    # ── SEBI fees ──
    sebi = 0.0
    if cfg.sebi_fees_enabled and traded_value > 0:
        sebi = round(traded_value / CRORE * cfg.sebi_fees_per_crore, 2)

    total = round(slippage + brokerage + exchange_tc + stt + stamp_duty + gst + sebi, 2)
    return CostEstimate(
        segment=seg.value,
        traded_value=round(traded_value, 2),
        slippage=slippage,
        brokerage=brokerage,
        exchange_tc=exchange_tc,
        stt=stt,
        stamp_duty=stamp_duty,
        gst=gst,
        sebi=sebi,
        total=total,
    )


def estimate_round_trip(
    side: str,
    entry_value: float,
    exit_value: float,
    segment: CostSegment | str,
    qty: float = 0.0,
    slippage_entry: float = 0.0,
    slippage_exit: float = 0.0,
    config: BacktestCostConfig | None = None,
) -> CostEstimate:
    """Convenience: total costs across an entry + exit round trip (both legs)."""
    entry = estimate_cost(side, entry_value, segment, qty, slippage_value=slippage_entry, config=config)
    exit_side = "SELL" if side.upper() == "BUY" else "BUY"
    exit_c = estimate_cost(exit_side, exit_value, segment, qty, slippage_value=slippage_exit, config=config)
    return CostEstimate(
        segment=segment.value if isinstance(segment, CostSegment) else str(segment),
        traded_value=round(entry.traded_value + exit_c.traded_value, 2),
        slippage=round(entry.slippage + exit_c.slippage, 2),
        brokerage=round(entry.brokerage + exit_c.brokerage, 2),
        exchange_tc=round(entry.exchange_tc + exit_c.exchange_tc, 2),
        stt=round(entry.stt + exit_c.stt, 2),
        stamp_duty=round(entry.stamp_duty + exit_c.stamp_duty, 2),
        gst=round(entry.gst + exit_c.gst, 2),
        sebi=round(entry.sebi + exit_c.sebi, 2),
        total=round(entry.total + exit_c.total, 2),
    )

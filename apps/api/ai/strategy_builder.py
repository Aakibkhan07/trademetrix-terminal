import json
import logging

from ai.openrouter import chat_completion
from ai.training_context import STRATEGY_RECOMMENDATIONS, BUILDER_GUIDE

logger = logging.getLogger(__name__)

BUILD_SYSTEM_PROMPT = """You are TradeMetrix AI Strategy Builder. You convert natural language trading ideas into structured JSON for the TradeMetrix visual strategy builder.

Available block types:
- source.candle, source.close_history, source.market_time, source.position, source.portfolio
- indicator.ema, indicator.sma, indicator.rsi, indicator.macd, indicator.bollinger, indicator.vwap, indicator.atr, indicator.supertrend, indicator.stoch, indicator.adx, indicator.ichimoku
- signal.cross_above, signal.cross_below, signal.threshold, signal.breakout, signal.divergence, signal.confirmation
- order.buy, order.sell, order.exit, order.reverse, order.sl, order.target, order.trailing_sl
- logic.and, logic.or, logic.not, logic.gt, logic.lt, logic.gte, logic.lte, logic.eq
- math.add, math.sub, math.mul, math.div, math.min, math.max, math.avg, math.abs
- candle.bullish, candle.bearish, candle.doji, candle.hammer, candle.engulfing, candle.pin_bar
- risk.drawdown, risk.max_loss, risk.max_trades
- time.market_hour, time.market_session, time.day_of_week, time.time_range, time.expiry
- constant.number, constant.string, constant.boolean
- portfolio.position_size, portfolio.open_positions, portfolio.position_pnl

You must respond ONLY with valid JSON. No markdown, no explanation.

The JSON schema must be:
{
  "name": "Strategy name",
  "description": "Brief description",
  "settings": {
    "symbol": "NIFTY or BANKNIFTY or FINNIFTY",
    "exchange": "NSE",
    "interval": "1m, 5m, 15m, 30m, 1h, 1d",
    "max_positions": 1,
    "max_risk_per_trade": 0,
    "max_daily_trades": 0,
    "trigger": "CANDLE_CLOSE",
    "require_confirmation": false
  },
  "nodes": [
    {
      "block_type": "source.candle",
      "params": {},
      "position": {"x": 50, "y": 50}
    }
  ],
  "edges": [
    {
      "source_node": "n0",
      "source_port": "close",
      "target_node": "n1",
      "target_port": "source"
    }
  ],
  "tags": ["tag1", "tag2"]
}

Rules:
- Node IDs are auto-generated as "n0", "n1", "n2", etc. in order of the nodes array.
- Position x increases by 250 for each column, y by 150 for each row.
- Every non-source node must have all its required inputs connected via edges.
- At minimum: one source.candle node, and one order.buy or order.sell node.
- Use trailing_sl or target nodes for risk management when user asks.
- Keep it simple — 3-8 nodes is ideal for a working strategy."""

async def build_strategy_from_prompt(prompt: str) -> dict | None:
    try:
        text = await chat_completion(
            BUILD_SYSTEM_PROMPT + "\n\nUser request: " + prompt + "\n\nRespond ONLY with JSON.",
            max_tokens=2000,
        )
        if text is None:
            return None

        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        parsed = json.loads(text)

        required = ["name", "nodes", "edges"]
        for key in required:
            if key not in parsed:
                logger.error("AI strategy missing required key: %s", key)
                return None

        return parsed
    except json.JSONDecodeError as e:
        logger.error("AI strategy JSON parse error: %s", e)
        return None
    except Exception as e:
        logger.error("AI strategy build error: %s", e, exc_info=True)
        return None

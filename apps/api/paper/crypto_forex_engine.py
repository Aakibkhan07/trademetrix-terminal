"""
Paper-only execution engine for crypto and forex.
SAFETY: This module NEVER places a real order on any exchange.
All fills are simulated against real market prices from public feeds.
NO live/real-money path exists here — no broker API keys, no exchange routing.
"""
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from market.crypto_feed import crypto_feed
from market.forex_feed import forex_feed

logger = logging.getLogger(__name__)

ASSET_CLASSES = {"crypto", "forex"}


class VirtualPosition:
    def __init__(self, symbol: str, asset_class: str):
        self.symbol = symbol
        self.asset_class = asset_class
        self.quantity = 0.0
        self.entry_price = 0.0
        self.realized_pnl = 0.0

    @property
    def current_price(self) -> float | None:
        if self.asset_class == "crypto":
            return crypto_feed.get_price(self.symbol)
        return forex_feed.get_price(self.symbol)

    @property
    def unrealized_pnl(self) -> float:
        cp = self.current_price
        if cp is None:
            return 0.0
        return self.quantity * (cp - self.entry_price)

    def to_dict(self) -> dict:
        cp = self.current_price
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "quantity": round(self.quantity, 8),
            "entry_price": round(self.entry_price, 6),
            "current_price": round(cp, 6) if cp else 0,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "realized_pnl": round(self.realized_pnl, 2),
        }


class VirtualAccount:
    def __init__(self, user_id: str, initial_balance: float = 10000.0):
        self.user_id = user_id
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions: dict[str, VirtualPosition] = {}
        self.orders: list[dict] = []
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.trade_count = 0

    @property
    def equity(self) -> float:
        return self.balance + sum(p.unrealized_pnl for p in self.positions.values())

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "balance": round(self.balance, 2),
            "initial_balance": self.initial_balance,
            "equity": round(self.equity, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_fees": round(self.total_fees, 2),
            "trade_count": self.trade_count,
            "open_positions": len([p for p in self.positions.values() if abs(p.quantity) > 1e-12]),
        }


class CryptoForexPaperEngine:
    """
    Paper execution engine for crypto and forex.
    SAFETY BOUNDARY: All methods operate on virtual accounts only.
    No connection to any exchange or broker API for order execution.
    No real API keys stored or used.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._accounts: dict[str, VirtualAccount] = {}
        self._slippage_pct = 0.05
        self._order_counter = 0

    def get_or_create_account(self, user_id: str, initial_balance: float = 10000.0) -> VirtualAccount:
        if user_id not in self._accounts:
            self._accounts[user_id] = VirtualAccount(user_id, initial_balance)
        return self._accounts[user_id]

    def get_account(self, user_id: str) -> VirtualAccount | None:
        return self._accounts.get(user_id)

    async def _current_price(self, asset_class: str, symbol: str) -> float | None:
        s = symbol.upper()
        if asset_class == "crypto":
            return crypto_feed.get_price(s)
        return forex_feed.get_price(s)

    async def pairs(self, asset_class: str) -> list[dict]:
        if asset_class == "crypto":
            return [
                {
                    "symbol": s.upper(),
                    "price": crypto_feed.get_price(s.upper()),
                    "change_pct": (crypto_feed.get_ticker(s.upper()) or {}).get("change_pct", 0),
                    "volume": (crypto_feed.get_ticker(s.upper()) or {}).get("volume", 0),
                }
                for s in crypto_feed.latest_prices
            ]
        return [
            {
                "symbol": s,
                "price": data["price"],
                "change_pct": 0,
                "volume": 0,
            }
            for s, data in forex_feed.latest_prices.items()
        ]

    async def place_order(
        self,
        user_id: str,
        asset_class: str,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> dict:
        if asset_class not in ASSET_CLASSES:
            return {"success": False, "message": f"Unknown asset class: {asset_class}"}

        account = self.get_or_create_account(user_id)
        sym = symbol.upper()
        current = await self._current_price(asset_class, sym)

        if current is None:
            return {
                "success": False,
                "message": f"No price available for {sym}. Ensure the data feed is running.",
            }

        if order_type == "market":
            if side == "buy":
                fill_price = current * (1 + self._slippage_pct / 100)
            else:
                fill_price = current * (1 - self._slippage_pct / 100)
        elif order_type == "limit":
            if price is None or price <= 0:
                return {"success": False, "message": "Price required for limit orders"}
            if (side == "buy" and current > price) or (side == "sell" and current < price):
                return {
                    "success": False,
                    "status": "pending",
                    "message": f"Limit not triggered. Current: {current:.4f}, Limit: {price:.4f}",
                }
            fill_price = price
        else:
            return {"success": False, "message": f"Unsupported order type: {order_type}"}

        cost = quantity * fill_price

        if side == "buy":
            if cost > account.balance:
                return {
                    "success": False,
                    "message": f"Insufficient balance. Need ${cost:.2f}, have ${account.balance:.2f}",
                }
            account.balance -= cost
        else:
            pos = account.positions.get(sym)
            if not pos or pos.quantity < quantity - 1e-12:
                return {
                    "success": False,
                    "message": f"Insufficient position. Have {pos.quantity if pos else 0:.6f} {sym}, want to sell {quantity:.6f}",
                }

        self._order_counter += 1
        order_id = f"cf_paper_{self._order_counter}_{int(time.time())}"

        pos = account.positions.setdefault(sym, VirtualPosition(sym, asset_class))

        if side == "buy":
            new_qty = pos.quantity + quantity
            pos.entry_price = ((pos.entry_price * pos.quantity) + (fill_price * quantity)) / new_qty if new_qty > 0 else fill_price
            pos.quantity = new_qty
        else:
            realized = quantity * (fill_price - pos.entry_price)
            pos.realized_pnl += realized
            account.total_pnl += realized
            pos.quantity -= quantity
            account.balance += cost + realized

        account.trade_count += 1

        record = {
            "order_id": order_id,
            "asset_class": asset_class,
            "symbol": sym,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "fill_price": round(fill_price, 6),
            "cost": round(cost, 2),
            "balance_after": round(account.balance, 2),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        account.orders.append(record)

        return {
            "success": True,
            "order_id": order_id,
            "symbol": sym,
            "side": side,
            "quantity": quantity,
            "fill_price": round(fill_price, 6),
            "cost": round(cost, 2),
            "balance": round(account.balance, 2),
            "current_price": round(current, 6),
            "message": f"{side.upper()} {quantity} {sym} @ {fill_price:.6f}",
        }

    def get_positions(self, user_id: str) -> list[dict]:
        account = self._accounts.get(user_id)
        if not account:
            return []
        return [p.to_dict() for p in account.positions.values() if abs(p.quantity) > 1e-12]

    def get_account_summary(self, user_id: str) -> dict | None:
        account = self._accounts.get(user_id)
        if not account:
            return None
        return account.to_dict()

    def get_orders(self, user_id: str, limit: int = 50) -> list[dict]:
        account = self._accounts.get(user_id)
        if not account:
            return []
        return sorted(account.orders, key=lambda o: o["timestamp"], reverse=True)[:limit]

    def reset_account(self, user_id: str, initial_balance: float = 10000.0) -> VirtualAccount:
        self._accounts[user_id] = VirtualAccount(user_id, initial_balance)
        return self._accounts[user_id]


crypto_forex_engine = CryptoForexPaperEngine()

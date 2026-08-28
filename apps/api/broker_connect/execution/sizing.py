"""
Reference position sizer: capital-fraction model.

qty = floor( (capital * risk_fraction) / (ref_price * lot_size) ) * lot_size,
capped at max_lots. Swap in your own by implementing the PositionSizer port.
"""

from __future__ import annotations

import math

from .models import Signal, UserTradingProfile


class CapitalFractionSizer:
    def size(self, profile: UserTradingProfile, signal: Signal) -> int:
        if profile.capital <= 0 or signal.ref_price <= 0:
            return 0

        budget = profile.capital * max(0.0, profile.risk_fraction)
        cost_per_lot = signal.ref_price * signal.lot_size
        if cost_per_lot <= 0:
            return 0

        lots = math.floor(budget / cost_per_lot)
        lots = max(0, min(lots, profile.max_lots))
        return lots * signal.lot_size

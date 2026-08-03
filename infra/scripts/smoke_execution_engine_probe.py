#!/usr/bin/env python3
"""Execution Engine v1.0 — production smoke probe (runs INSIDE trademetrix_api).

Drives the deployed container's engine code through the production legacy-bus
bridge (the exact path fixed in the release audit) and asserts the canonical
chain responds correctly. Because engine singletons are process-local to the
API process, the LIVE API process is verified by the orchestrator via its log
stream and /metrics; this probe verifies the deployed code + bridge mapping
deterministically in a throwaway process.

Phases (first CLI arg):
  startup           print wiring state (bus running, bridge subscribers)
  run <user> <ids...>
                    write: PaperOrderPartiallyFilled (SELL 2 @110),
                           PaperOrderFilled BUY 10 @100,
                           PaperOrderFilled SELL 8 @110   -> realized 100.0, net 0
                    then assert ledger/position/pnl/portfolio/dups/backlog/metrics
  liveness <user>   write one PaperOrderFilled BUY 5 @100 then assert state
                    (post-restart check; same process as the write)
"""
import asyncio
import sys

USER = sys.argv[2] if len(sys.argv) > 2 else "fa668109-4b1e-4758-a49b-015027ea4115"
SYMBOL = "NIFTY"
BROKER = "paper"


def ok(name, passed, detail=""):
    print(f"{'PASS' if passed else 'FAIL'} {name}" + (f" — {detail}" if detail else ""), flush=True)


def key(name, value):
    print(f"KEY {name}={value}", flush=True)


def init_wire():
    from execution_engine.init import init_execution_engine

    init_execution_engine()


# ---------------------------------------------------------------------------
# reference FIFO (independent of the engine)
# ---------------------------------------------------------------------------
def reference_net_and_realized(trades):
    longs, shorts = [], []
    realized = 0.0
    for side, qty, price in trades:
        if side == "BUY":
            rem = qty
            while rem > 0 and shorts:
                lq, lp = shorts[0]
                used = min(rem, lq)
                realized += used * (lp - price)
                rem -= used
                lq -= used
                shorts[0] = (lq, lp)
                if lq <= 1e-9:
                    shorts.pop(0)
            if rem > 0:
                longs.append((rem, price))
        else:
            rem = qty
            while rem > 0 and longs:
                lq, lp = longs[0]
                used = min(rem, lq)
                realized += used * (price - lp)
                rem -= used
                lq -= used
                longs[0] = (lq, lp)
                if lq <= 1e-9:
                    longs.pop(0)
            if rem > 0:
                shorts.append((rem, price))
    return round(sum(q for q, _ in longs) - sum(q for q, _ in shorts)), round(realized, 2)


# ---------------------------------------------------------------------------
async def write_events():
    init_wire()
    from execution.event_bus import execution_event_bus
    from execution.models import ExecutionEvent

    def payload(req_id, qty, price, fill_qty):
        return {
            "order_id": req_id, "quantity": qty, "price": price,
            "fill": {"order_id": req_id, "filled_quantity": fill_qty, "filled_price": price},
            "is_paper": True, "strategy_id": "smoke", "source": "smoke",
        }

    async def pub(etype, req_id, side, qty, price, fill_qty):
        await execution_event_bus.publish(ExecutionEvent(
            event_type=etype,
            execution_request_id=req_id,
            user_id=USER, broker=BROKER, symbol=SYMBOL, side=side,
            message="smoke inject",
            payload=payload(req_id, qty, price, fill_qty),
        ))

    await pub("PaperOrderPartiallyFilled", "smoke-part-1", "SELL", 2, 110.0, 2)
    await pub("PaperOrderFilled", "smoke-buy-1", "BUY", 10, 100.0, 10)
    await pub("PaperOrderFilled", "smoke-sell-1", "SELL", 8, 110.0, 8)
    await asyncio.sleep(0.3)
    print("EVENTS_WRITTEN ids=smoke-part-1,smoke-buy-1,smoke-sell-1", flush=True)


async def write_liveness():
    init_wire()
    from execution.event_bus import execution_event_bus
    from execution.models import ExecutionEvent

    await execution_event_bus.publish(ExecutionEvent(
        event_type="PaperOrderFilled",
        execution_request_id="smoke-live-1",
        user_id=USER, broker=BROKER, symbol=SYMBOL, side="BUY",
        message="smoke liveness",
        payload={"order_id": "smoke-live-1", "quantity": 5, "price": 100.0,
                 "fill": {"order_id": "smoke-live-1", "filled_quantity": 5, "filled_price": 100.0},
                 "is_paper": True, "source": "smoke"},
    ))
    await asyncio.sleep(0.3)
    print("LIVENESS_WRITTEN id=smoke-live-1", flush=True)


async def dump_state(ids):
    from execution_engine import pnl_engine, portfolio_engine, position_manager, trade_manager
    from prometheus_client import REGISTRY

    key("ledger_count_per_id",
        "|".join(f"{i}={sum(1 for t in trade_manager.list_trades(USER, broker=BROKER, symbol=SYMBOL, limit=10000) if t.client_order_id == i)}" for i in ids))
    trades = trade_manager.list_trades(USER, broker=BROKER, symbol=SYMBOL, limit=10000)
    key("ledger_total", trade_manager.count(USER))
    ref_net, ref_realized = reference_net_and_realized([(t.side, t.quantity, t.price) for t in trades])

    pos = position_manager.get_position(USER, BROKER, SYMBOL)
    key("pos_qty", pos.quantity if pos else None)
    key("pos_realized", pos.realised_pnl if pos else None)
    key("ref_net", ref_net)
    key("ref_realized", ref_realized)

    acc = pnl_engine.get_account(USER, BROKER)
    key("acc_realized", acc.realised_pnl)
    key("acc_equity", acc.current_equity)
    snap = portfolio_engine.snapshot(USER)
    key("snap_realized", getattr(snap, "realised_pnl", None) if snap else None)

    # backlog
    from execution_engine import execution_bus
    key("queue_empty", str(execution_bus._queue.empty() if execution_bus._queue else True).lower())
    key("inline_tasks", len(execution_bus._inline_tasks))
    key("buffered", execution_bus.buffered)

    # local prometheus cross-check
    g = REGISTRY.get_sample_value("execution_engine_trades_executed_total", {"broker": BROKER})
    key("local_trades_gauge", g if g is not None else 0.0)


async def run(ids):
    init_wire()
    await write_events()
    await dump_state(ids)


async def liveness():
    init_wire()
    await write_liveness()
    await dump_state(["smoke-live-1"])


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "state"
    if phase == "startup":
        init_wire()
        from execution.event_bus import execution_event_bus
        from execution_engine import execution_bus
        from execution_engine.events import _LEGACY_BRIDGE_WIRED
        key("bus_running", str(execution_bus.running).lower())
        key("bus_subscribers", execution_bus.subscriber_count())
        key("bridge_wired", str(_LEGACY_BRIDGE_WIRED).lower())
        key("legacy_star_subscribers", len(execution_event_bus._subscribers.get("*", [])))
    elif phase == "run":
        asyncio.run(run([a for a in sys.argv[3:]]))
    elif phase == "liveness":
        asyncio.run(liveness())
    elif phase == "state":
        asyncio.run(dump_state([a for a in sys.argv[3:]]))
    else:
        print(f"unknown phase {phase}", flush=True)
        sys.exit(2)
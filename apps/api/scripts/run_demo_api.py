"""Run the API locally with a seeded demo tenant, so the money pages have something to show.

**Demo tooling. Never run this against production.**

Why it exists: `/paper`, `/portal`, `/terminal` and `/funds` read from `position_manager` and
`pnl_engine`, which are in-memory and hydrate from nothing — `positions_snapshot` is only read
by the admin view. So a fresh local database shows every money page empty, which makes it
impossible to look at the rendering fixes without placing real orders first.

The seed therefore goes through the **real** code path rather than writing fields directly:
it publishes `trade_event`s on the execution bus, exactly as a fill does, and lets
`position_manager._on_trade_event` run the actual FIFO arithmetic. Every number you see —
`average_buy_price`, `average_sell_price`, signed `quantity`, `side`, `realised_pnl` — is
computed by the engine, not by this file. `mark_to_market` then revalues positions through
`FifoLots.unrealized_pnl`, which is likewise the production logic.

The data is chosen so each rendering fix has something to show:

* a **profitable long** — `/paper`'s Side column must be green (`isLong`, not `side === 'BUY'`)
* a **profitable short** — the fix in `lib/positions.ts`: a short trading below its entry is a
  profit, and must render as a positive number, not a loss
* a **losing short** — the same arithmetic the other way, so a sign flip cannot pass by luck
* a **closed round trip** — non-zero `realised_pnl`, so `/funds`' cumulative tiles are not all
  the zero they used to show

`is_market_open()` is forced True. Without it `/paper/positions` takes its closed-market
branch, leaves `last_price` at the entry price and shows no movement at all — which is correct
behaviour for a closed market, and useless for looking at anything. That is the one thing here
that fakes a condition rather than seeding data, and it is confined to this launcher.

Usage:

    cp .env.test .env          # the API must talk to the LOCAL Supabase
    python scripts/run_demo_api.py --user <uuid>

Create the tenant first, through the local GoTrue admin API so the password is hashed
correctly and the `profiles` trigger fires:

    curl -X POST http://localhost:54321/auth/v1/admin/users \
      -H "apikey: $SUPABASE_SERVICE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
      -H 'Content-Type: application/json' \
      -d '{"email":"demo.trader@trademetrix.dev","password":"Demo@2026!","email_confirm":true}'

**The email domain has to be a real one.** `SignInRequest.email` is pydantic `EmailStr`, and
`email-validator` rejects special-use names — `.local`, `.test`, `.example`, `example.com` —
with a 422 before the request reaches any code. A first attempt at `demo@trademetrix.local`
failed exactly this way, which reads like a credentials problem rather than a validator one.

Refuses to start if `SUPABASE_URL` is not local, for the same reason the database tests do:
this process would otherwise issue UPDATEs against the live credentials table.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("TM_DEMO", "1")


def _assert_local_database() -> None:
    """Refuse to run anywhere but the local stack."""
    from dotenv import load_dotenv

    load_dotenv(API_ROOT / ".env", override=True)
    url = os.environ.get("SUPABASE_URL", "")
    if not url:
        sys.exit("SUPABASE_URL is not set — is .env present?")
    if "localhost" not in url and "127.0.0.1" not in url:
        sys.exit(
            f"refusing to run: SUPABASE_URL={url!r} is not a local database.\n"
            "This launcher seeds in-memory engines and issues writes; against production it\n"
            "would touch the live broker_credentials table. Use: cp .env.test .env"
        )
    print(f"database: {url}  (local, confirmed)")


# ── the demo book ───────────────────────────────────────────────────────────
# (symbol, side, quantity, price) — one row per fill.
#
# RELIANCE is bought and sold, so it closes flat and leaves realised P&L behind. The three
# that stay open are what the position tables render.
FILLS = [
    ("NSE:RELIANCE-EQ", "BUY", 40, 1280.00),
    ("NSE:RELIANCE-EQ", "SELL", 40, 1312.50),   # closed, +1300 realised
    ("NSE:NIFTY50-INDEX", "BUY", 15, 24520.00),  # long, and it is up
    ("NSE:BANKNIFTY-INDEX", "SELL", 12, 51300.00),  # short, and it is DOWN = profit
    ("NSE:FINNIFTY-INDEX", "SELL", 20, 23400.00),  # short, and it is UP = loss
]

# Where those symbols trade now, relative to their entry.
#
# BANKNIFTY is the one to look at: sold at 51300, marked at 50850, so a short is up 540 per
# point. Before the `lib/positions.ts` fix this row showed a large *loss* and was coloured
# red, because the page multiplied a negative quantity by a positive price move against the
# long basis price.
MARKET_PRICES = {
    "NSE:NIFTY50-INDEX": 24785.00,    # long  +3975
    "NSE:BANKNIFTY-INDEX": 50850.00,  # short +5400
    "NSE:FINNIFTY-INDEX": 23560.00,   # short -3200
}


async def seed(user_id: str, broker: str = "paper") -> None:
    from execution_engine import position_manager
    from execution_engine.events import ExecutionDomain, execution_bus, trade_event

    position_manager.install()

    for i, (symbol, side, qty, price) in enumerate(FILLS):
        execution_bus.publish(
            trade_event(
                user_id=user_id,
                broker=broker,
                order_id=f"demo-order-{i}",
                client_order_id=f"demo-{i}",
                correlation_id=f"demo-{i}",
                symbol=symbol,
                side=side,
                quantity=qty,
                price=price,
                message=f"demo fill {side} {qty} {symbol} @ {price}",
                payload={"trade_id": f"demo-trade-{i}", "account": "DEMO"},
            )
        )

    # The bus is not started, so `publish` takes the inline path, which wraps an async
    # handler in a fire-and-forget task (`ExecutionEngineBus._dispatch_inline`). Publishing
    # five fills in a row without yielding means none of those tasks has run when the code
    # below reads the book, and it comes back empty — which looks exactly like the fills
    # having been rejected. Yield long enough for them to complete.
    #
    # Not `sleep(0)`: each handler publishes a position event in turn, so the work spans more
    # than one scheduling round.
    await asyncio.sleep(0.25)

    updated = position_manager.mark_to_market(user_id, broker, MARKET_PRICES)
    print(f"\nseeded {len(FILLS)} fills, revalued {len(updated)} open positions\n")

    header = f"{'symbol':<22}{'side':<7}{'qty':>6}{'avg':>12}{'last':>12}{'unrealised':>13}"
    print(header)
    print("-" * len(header))
    for p in position_manager.get_positions(user_id, broker=broker):
        print(
            f"{p.symbol:<22}{p.side:<7}{p.quantity:>6}"
            f"{p.average_price:>12,.2f}{p.last_price:>12,.2f}{p.unrealised_pnl:>13,.2f}"
        )
    total = position_manager.aggregate_pnl(user_id, broker=broker)
    print("-" * len(header))
    print(f"{'TOTAL':<29}{'':<18}{total.get('unrealised_pnl', 0):>13,.2f}")


def seed_database(user_id: str, broker: str = "paper") -> None:
    """Write the rows the read paths reach for that the in-memory engines do not cover.

    Two things only exist in the database:

    * a **running PAPER run** in `strategy_runs`, which is the first branch
      `EngineService.get_funds` takes. Without it that method falls through to
      `get_active_broker`, which reads `broker_credentials` — and `paper` is not a value the
      broker CHECK constraint allows, so there would be no way to point a local tenant at the
      offline PaperBroker. With it, `/engine/funds` resolves a `PaperBroker` adapter and
      returns real margin figures instead of the no-broker stub.
    * a **`positions_snapshot`** row per open position, which is what
      `PositionService.list_all_positions` and `portfolio_manager._get_db_positions` read.

    What this deliberately does **not** do is fake a broker response to populate
    `PortfolioState.pnl`. `portfolio_manager` computes that field only from a live adapter's
    `get_pnl`, and stubbing one would produce a `/funds` page that looks right and tells you
    nothing about what the real endpoint does. So `/analytics/pnl` stays empty locally and the
    Funds page shows dashes for the cumulative tiles — which is the honest state, and is itself
    worth looking at, since a dash is what the fix renders where the old code rendered ₹0.
    """
    import subprocess

    def sql(statement: str) -> None:
        proc = subprocess.run(
            ["docker", "exec", "-i", "supabase_db_trademetrix-terminal",
             "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", statement],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"psql failed: {proc.stderr.strip()}")

    # `strategy_runs.strategy_id` is a uuid column, so the demo run needs a real one rather
    # than a readable slug. This is the same schema debt AGENTS.md records: builder strategies
    # are minted as 12-hex ids that this column cannot hold, which is why builder runs are
    # inserted with a try/except in `engine/graph_strategy_runner`. Not this task to fix —
    # noted only because it dictated the value used here.
    demo_run_id = "00000000-0000-4000-8000-00000000d370"

    # `strategy_runs.strategy_id` also carries a foreign key to `strategies.id`, so the run
    # needs a parent row. Idempotent: remove both, then re-insert.
    sql(f"DELETE FROM strategy_runs WHERE user_id = '{user_id}' AND strategy_id = '{demo_run_id}';")
    sql(f"DELETE FROM strategies WHERE id = '{demo_run_id}';")
    sql(
        "INSERT INTO strategies (id, user_id, name, type, config, is_active) "
        f"VALUES ('{demo_run_id}', '{user_id}', 'Demo Paper Strategy', 'builtin', '{{}}'::jsonb, true);"
    )
    sql(
        "INSERT INTO strategy_runs (user_id, strategy_id, broker, mode, symbols, status, "
        "started_at) VALUES "
        f"('{user_id}', '{demo_run_id}', '{broker}', 'PAPER', "
        "ARRAY['NSE:NIFTY50-INDEX','NSE:BANKNIFTY-INDEX','NSE:FINNIFTY-INDEX'], 'running', now());"
    )

    sql(f"DELETE FROM positions_snapshot WHERE user_id = '{user_id}' AND broker = '{broker}';")
    for symbol, qty, avg_buy, avg_sell, unreal, realised in (
        ("NSE:NIFTY50-INDEX", 15, 24520.00, 0.0, 3975.00, 0.0),
        ("NSE:BANKNIFTY-INDEX", -12, 0.0, 51300.00, 5400.00, 0.0),
        ("NSE:FINNIFTY-INDEX", -20, 0.0, 23400.00, -3200.00, 0.0),
    ):
        sql(
            "INSERT INTO positions_snapshot (user_id, broker, symbol, exchange, quantity, "
            "buy_quantity, sell_quantity, average_buy_price, average_sell_price, "
            "unrealised_pnl, realised_pnl, m2m, product, snapshot_at) VALUES "
            f"('{user_id}', '{broker}', '{symbol}', 'NSE', {qty}, {max(qty, 0)}, {max(-qty, 0)}, "
            f"{avg_buy:.2f}, {avg_sell:.2f}, {unreal:.2f}, {realised:.2f}, {unreal + realised:.2f}, "
            "'INTRADAY', now());"
        )
    print(f"seeded database rows: 1 PAPER run + 3 position snapshots for {user_id}")


def main() -> None:
    _assert_local_database()

    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True, help="demo tenant's user id")
    parser.add_argument("--broker", default="paper")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="seed, print the resulting book, and exit without serving. Lets the numbers the "
             "engine produced be checked without leaving a server running.",
    )
    args = parser.parse_args()

    # Force the market-open branch so `/paper/positions` runs its simulation path. Confined
    # to this process, and the only fabricated condition in the launcher.
    import market.status as market_status

    market_status.market_status_service.is_market_open = lambda: True

    seed_database(args.user, args.broker)
    asyncio.run(seed(args.user, args.broker))

    if args.seed_only:
        return

    import uvicorn

    print(f"\nAPI on http://{args.host}:{args.port}  (demo tenant {args.user})\n")
    uvicorn.run("main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

"""Controlled READ-ONLY Dhan Live Market Feed integration check.

Runs inside the API container so the credential is decrypted and used in-process and
never crosses to the operator's machine or appears in output.

Strictly market-data only. This script imports no order-placement path and calls none.
Usage:  python -m scripts.dhan_feed_live_check
"""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

# ── step 1: identify and verify the authorised credential (no value printed) ──
from core.db import get_supabase  # noqa: E402
from core.security import decrypt_broker_credentials  # noqa: E402

OWNER_EMAIL = "admin@trademetrix.tech"


def load_credential():
    s = get_supabase()
    cred = s.table("broker_credentials").select(
        "user_id,broker,role,token_status,encrypted_api_key,"
        "encrypted_access_token,encrypted_secret_key"
    ).eq("broker", "dhan").execute()
    prof = s.table("profiles").select("id,email,role").execute()
    by_id = {p["id"]: p for p in prof.data}

    print("── credential inventory (no values shown) ──")
    for c in cred.data:
        p = by_id.get(c["user_id"], {})
        print(f"   {p.get('email','<none>'):<42} role={p.get('role') or '-':<12} "
              f"token_status={c.get('token_status')}")
    owner = next((c for c in cred.data
                  if by_id.get(c["user_id"], {}).get("email") == OWNER_EMAIL), None)
    if owner is None:
        print("BLOCKED: no credential for the authorised owner account.")
        sys.exit(2)
    print(f"   -> using the authorised owner account ({OWNER_EMAIL}); token never printed.")

    client_id = (decrypt_broker_credentials(owner["encrypted_api_key"])
                 if owner.get("encrypted_api_key") else "")
    # Mirror DhanAdapter.authenticate exactly: it uses access_token when present and
    # otherwise falls back to secret_key. An earlier version of this script read only
    # encrypted_access_token, found it NULL, and declared the credential unusable --
    # which was wrong, because Dhan stores the usable token in encrypted_secret_key.
    access_token = (decrypt_broker_credentials(owner["encrypted_access_token"])
                    if owner.get("encrypted_access_token") else "")
    if not access_token and owner.get("encrypted_secret_key"):
        access_token = decrypt_broker_credentials(owner["encrypted_secret_key"])
        token_source = "encrypted_secret_key (adapter fallback)"
    else:
        token_source = "encrypted_access_token"
    if not access_token or not client_id:
        print("BLOCKED: neither access_token nor secret_key could be decrypted.")
        sys.exit(2)
    print(f"   -> token source: {token_source}")
    print(f"   -> client_id present: {bool(client_id)}   token present: {bool(access_token)}"
          f"   (lengths only: {len(client_id)}/{len(access_token)})")
    return client_id, access_token


async def main():
    client_id, access_token = load_credential()

    print("\n── market clock ──")
    ist = datetime.now(UTC).astimezone()
    print(f"   UTC {datetime.now(UTC):%Y-%m-%d %H:%M:%S}   IST {ist:%Y-%m-%d %H:%M:%S} "
          f"({ist:%a})  NSE cash session 09:15-15:30 IST")

    # ── step 4: resolve one NIFTY option from the authoritative master ──
    print("\n── resolving ONE contract from the Dhan instrument master ──")
    import httpx
    from market.dhan_instruments import DhanInstrumentProvider

    url = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
    text = httpx.get(url, timeout=180.0, follow_redirects=True).text
    provider = DhanInstrumentProvider(fetch=lambda u, t: text)
    health = await provider.refresh()
    print(f"   master: {health.row_count} contracts, status={health.validation_status}, "
          f"index options={health.index_option_count}")

    import market.dhan_instruments as di
    di.dhan_instrument_provider._dataset = provider.dataset

    from market.dhan_feed import (FeedMode, build_subscribe_frame, build_unsubscribe_frame,
                                  nearest_expiry, atm_strike, subscription_for_contract)

    results = {}

    async def run_batch(label, specs):
        subs = []
        for underlying, otype in specs:
            exp = nearest_expiry(underlying)
            if not exp:
                print(f"   {underlying:<10} {otype}: no eligible expiry in the master")
                continue
            strike = atm_strike(underlying, exp, option_type=otype)
            if strike is None:
                print(f"   {underlying:<10} {otype}: no listed strikes")
                continue
            sub = subscription_for_contract(underlying, expiry=exp, strike=strike,
                                            option_type=otype, mode=FeedMode.TICKER)
            inst = provider.resolve_option(underlying, expiry=exp, strike=strike,
                                           option_type=otype)
            subs.append(sub)
            print(f"   {underlying:<10} {otype}  exp={exp} strike={strike:<9} "
                  f"sym={inst.broker_symbol:<24} seg={sub.exchange_segment:<9} "
                  f"sid={sub.security_id} lot={inst.lot_size}")
        return subs

    print("\n── step 5/7: single contract subscription frame ──")
    single = await run_batch("single", [("NIFTY", "CE")])
    if not single:
        print("BLOCKED: could not resolve a NIFTY option from the master.")
        return 3
    frame = json.loads(build_subscribe_frame(single)[0])
    print(f"   frame: {json.dumps(frame)}")
    print(f"   -> segment is a derivative segment: "
          f"{frame['InstrumentList'][0]['ExchangeSegment'] != 'NSE_EQ'}")

    from market.dhan_feed import (DhanMarketEvent, DhanPacketError, FeedState, parse_packet,
                                  redact_url, build_url, DHAN_FEED_WSS_URL)

    print(f"\n── step 6/8: opening {DHAN_FEED_WSS_URL} (URL redacted in all output) ──")
    print(f"   redacted: {redact_url(build_url(access_token, client_id))}")
    import websockets

    received: list[DhanMarketEvent] = []
    control: list[dict] = []

    async def one_session(label, subs, budget_seconds=25.0):
        url = build_url(access_token, client_id)
        got: list[DhanMarketEvent] = []
        ctrl: list[dict] = []
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20,
                                          open_timeout=20, max_size=4 * 1024 * 1024) as ws:
                print(f"   [{label}] WEBSOCKET CONNECTED")
                for f in build_subscribe_frame(subs):
                    await ws.send(f)
                print(f"   [{label}] subscription frame(s) sent "
                      f"({len(subs)} instrument(s), RequestCode "
                      f"{json.loads(build_subscribe_frame(subs)[0])['RequestCode']})")
                deadline = asyncio.get_running_loop().time() + budget_seconds
                while asyncio.get_running_loop().time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    except asyncio.TimeoutError:
                        if got:
                            break
                        continue
                    if isinstance(raw, str):
                        ctrl.append({"type": "text", "body": raw[:200]})
                        continue
                    try:
                        parsed = parse_packet(raw)
                    except DhanPacketError as exc:
                        ctrl.append({"type": "unparsed", "error": str(exc), "len": len(raw)})
                        continue
                    if isinstance(parsed, dict):
                        ctrl.append(parsed)
                        if parsed.get("type") == "server_disconnect":
                            print(f"   [{label}] SERVER DISCONNECT code={parsed['code']} "
                                  f"reason={parsed['reason']} terminal={parsed['terminal']}")
                            break
                        continue
                    got.append(parsed)
                    print(f"   [{label}] packet type={parsed.packet_type:<8} len={len(raw):<4} "
                          f"seg={parsed.exchange_segment:<9} sid={parsed.security_id:<8} "
                          f"ts={parsed.timestamp:%H:%M:%S} ltp={parsed.ltp} "
                          f"bid={parsed.bid} ask={parsed.ask} vol={parsed.volume} "
                          f"oi={parsed.open_interest}")
                try:
                    for f in build_unsubscribe_frame(subs):
                        await ws.send(f)
                except Exception:
                    pass
        except websockets.exceptions.InvalidStatus as exc:
            print(f"   [{label}] HTTP handshake rejected: status={exc.response.status_code} "
                  f"{exc.response.reason!r}")
            return got, ctrl, ("http_status", exc.response.status_code)
        except websockets.exceptions.InvalidStatusCode as exc:
            print(f"   [{label}] HTTP status {exc.status_code}")
            return got, ctrl, ("http_status", exc.status_code)
        except Exception as exc:
            print(f"   [{label}] connection error: {type(exc).__name__}: {exc}")
            return got, ctrl, ("error", f"{type(exc).__name__}: {exc}")
        return got, ctrl, None

    got, ctrl, err = await one_session("single", single)
    received, control = got, ctrl
    print(f"   [{'single'}] packets={len(got)} control={len(ctrl)} err={err}")

    if err and err[0] == "http_status":
        print(f"\n   server said {err[1]}; stopping here without reinterpretation.")
        return 4

    print("\n── step 9: contract identity verification ──")
    subscribed = {s.identity for s in single}
    for ev in received:
        ok = (ev.exchange_segment, ev.security_id) in subscribed
        print(f"   received {ev.exchange_segment}/{ev.security_id} == subscribed: {ok}")
        back = provider.resolve_by_security_id(ev.security_id,
                                               exchange_segment=ev.exchange_segment,
                                               for_live=False)
        print(f"   resolves back to master contract: "
              f"{back is not None and back.security_id == ev.security_id}"
              f"  ({back.broker_symbol if back else 'NOT RESOLVED'})")

    print("\n── step 10/11: controlled batch of four ──")
    batch = await run_batch("batch", [("NIFTY", "CE"), ("NIFTY", "PE"),
                                      ("SENSEX", "CE"), ("360ONE", "CE")])
    got2, ctrl2, err2 = await one_session("batch", batch) if batch else ([], [], None)
    print(f"   [{'batch'}] packets={len(got2)} control={len(ctrl2)} err={err2}")
    batch_ids = {s.identity for s in batch}
    seen = {(e.exchange_segment, e.security_id) for e in got2}
    print(f"   subscribed identities : {len(batch_ids)}")
    print(f"   distinct identities seen : {len(seen)}")
    print(f"   every packet maps to a subscribed contract: "
          f"{all(i in batch_ids for i in seen)}")

    print("\n── step 12: controlled reconnect ──")
    if not got:
        print("   NOT TESTED — no data flow established, so a reconnect proves nothing.")
    else:
        async def resubscribe_probe():
            url = build_url(access_token, client_id)
            async with websockets.connect(url, ping_interval=20, open_timeout=20,
                                          max_size=4 * 1024 * 1024) as ws:
                for f in build_subscribe_frame(single):
                    await ws.send(f)
                got = []
                deadline = asyncio.get_running_loop().time() + 20
                while asyncio.get_running_loop().time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    except asyncio.TimeoutError:
                        if got:
                            break
                        continue
                    try:
                        p = parse_packet(raw)
                    except DhanPacketError:
                        continue
                    if isinstance(p, DhanMarketEvent):
                        got.append(p)
                return got

        before = len(received)
        after = await resubscribe_probe()
        print(f"   packets before reconnect: {before}")
        print(f"   packets after a fresh session resubscribed: {len(after)}")
        print(f"   subscription set restored: "
              f"{all((e.exchange_segment, e.security_id) in subscribed for e in after)}")

    print("\n── control frames seen ──")
    for c in control + ctrl2:
        print(f"   {c}")

    print("\n── summary (machine-readable) ──")
    print(json.dumps({
        "single_packets": len(received),
        "batch_packets": len(got2),
        "single_error": err,
        "batch_error": err2,
        "subscribed": sorted("/".join(i) for i in subscribed),
        "batch_subscribed": sorted("/".join(i) for i in batch_ids),
        "received": sorted({f"{e.exchange_segment}/{e.security_id}" for e in received}),
        "received_batch": sorted({f"{e.exchange_segment}/{e.security_id}" for e in got2}),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

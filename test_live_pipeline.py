import httpx
import asyncio

BASE = "https://api.ai.trademetrix.tech"

async def main():
    async with httpx.AsyncClient(base_url=BASE) as c:
        # --- AUTH ---
        r = await c.get("/api/v1/auth/csrf")
        csrf_token = r.json()["csrf_token"]
        csrf_cookie = r.cookies.get("csrf_token")
        print(f"[AUTH] CSRF: {csrf_token[:16]}...")

        r = await c.post("/api/v1/auth/signin",
            json={"email": "Aakibkhn2@gmail.com", "password": "Aakibkhan1@23"},
            cookies={"csrf_token": csrf_cookie}, headers={"x-csrf-token": csrf_token})
        session = dict(c.cookies)
        print(f"[AUTH] Signin: {'OK' if r.status_code == 200 else 'FAIL'}")

        def hd(): return {"x-csrf-token": csrf_token}
        def ck(): return {**session, "csrf_token": csrf_cookie}

        # 1. LIVE STATUS
        r = await c.get("/api/v1/risk/live/status", cookies=ck())
        print(f"\n1. LIVE mode: {'ON' if r.json().get('is_live') else 'OFF'}")

        # 2. KILL SWITCH
        for action in ["enable", "disable"]:
            r = await c.post(f"/api/v1/risk/kill-switch/{action}", cookies=ck(), headers=hd())
            print(f"2. Kill switch {action}: {r.json().get('message','?')}")

        # 3. UPDATE RISK SETTINGS
        r = await c.post("/api/v1/risk/settings",
            json={"max_daily_loss": 100000, "max_open_positions": 5, "max_drawdown_pct": 20},
            cookies=ck(), headers=hd())
        print(f"3. Update risk settings: {r.json().get('message', str(r.status_code))}")

        r = await c.get("/api/v1/risk/settings", cookies=ck())
        s = r.json().get("settings", [{}])[0]
        print(f"   Current: daily_loss={s.get('max_daily_loss')}, positions={s.get('max_open_positions')}, drawdown={s.get('max_drawdown_pct')}, live={s.get('is_live')}")

        # 4. DAILY LOSS FLOOR (try below tier minimum)
        r = await c.post("/api/v1/risk/settings", json={"max_daily_loss": 1}, cookies=ck(), headers=hd())
        print(f"4. Daily loss floor enforcement: {'PASS' if r.status_code == 400 else 'FAIL'} ({r.json().get('detail','')[:60]})")

        # 5. LIVE MODE TOGGLE
        r = await c.post("/api/v1/risk/live/disable", cookies=ck(), headers=hd())
        print(f"5a. LIVE disable: {r.json().get('message','?')}")

        r = await c.get("/api/v1/risk/live/status", cookies=ck())
        is_live = r.json().get("is_live", False)
        print(f"5b. LIVE status after disable: {'ON' if is_live else 'OFF'}")

        r = await c.post("/api/v1/risk/live/enable", json={"confirm": True}, cookies=ck(), headers=hd())
        print(f"5c. LIVE re-enable: {r.json().get('message','?')}")

        # 6. MAX STRATEGY ENFORCEMENT
        r = await c.post("/api/v1/buyer-strategies/activate",
            json={"strategy_id":"test-e2e-a","strategy_key":"momentum_breakout_buyer","index":"NIFTY","config":{}},
            cookies=ck(), headers=hd())
        print(f"6a. Activate strategy 1: {r.json().get('message','FAIL')}")

        r = await c.post("/api/v1/buyer-strategies/activate",
            json={"strategy_id":"test-e2e-b","strategy_key":"trend_rider_buyer","index":"NIFTY","config":{}},
            cookies=ck(), headers=hd())
        print(f"6b. Activate strategy 2: {r.json().get('message','FAIL')}")

        # Cleanup
        for sid in ["test-e2e-a", "test-e2e-b"]:
            await c.post(f"/api/v1/buyer-strategies/deactivate/{sid}", cookies=ck(), headers=hd())

        # 7. EMERGENCY STOP (via kill_switch module, verify audit log)
        print(f"\n{'='*20} API TESTS DONE {'='*20}")
        print("Check emergency stop via SSH: ssh root@187.127.185.56 'supabase ...'")


if __name__ == "__main__":
    asyncio.run(main())

# TradeMetrix Terminal — User Guide (Hinglish)

> **1 link se start:** `https://ai.trademetrix.tech` → Sign Up → Broker Connect → Paper Trade → Backtest → Live

---

## 1. Account Banao (30 sec)
1. `ai.trademetrix.tech/auth` pe jao → **Sign Up** → email + password → **Create Account**
2. OTP / Email verify karo → auto `/onboarding` pe jaoge → **Get Started** dabao
3. Aap `/live` (Live Dashboard) pe pahunch jaoge — yahi aapka cockpit hai

**Problem?** `/help` pe CLIARITY track + Feedback button se seedha message bhejo.

---

## 2. Broker Connect Karo (2 min) — sabse zaroori step
**Kyun?** Bina broker connect ke live order nahi lagega; paper trading bina broker ke bhi chalega.

### A) Fyers / Zerodha / Dhan / Upstox (OAuth — redirect)
1. `/brokers` pe **+ Connect Broker** dabao → apna broker chuno (e.g. **Fyers**)
2. `API Key` + `Secret Key` dalo — ye **aapke** Fyers app ke hain (`myapi.fyers.in` pe free app banao, `App ID` + `Secret` copy karo)
3. **Connect** dabao → Fyers login page khulega → **Allow** karo → wapas `/brokers` pe `Active` + `Token valid until ...` dikhega
4. **Token roz expire hota hai (SEBI rule)** — roz subah `Re-auth` dabake 10 sec me wapas active karo. Telegram pe `T-60min` alert bhi aayega.

### B) Angel One / Kotak Neo / 5Paisa (Credentials + TOTP)
1. `/brokers` → **Connect** → `Client Code` + `Password` + `API Key` (+ `TOTP Secret` agar hai) dalo → **Connect**
2. System khud `TOTP` generate karke login karega — `Active` dikhte hi done
3. Kotak Neo me `Consumer Key` + `Mobile` + `UCC` + `TOTP` + `MPIN` — Neo app → `More → Trade API → Generate` se `Consumer Key` lo

> **Security:** Aapka `Secret / TOTP` kabhi plain nahi dikhta — `broker_credentials` table me `encrypted_api_key` ke roop me save hota hai, sirf aapka active broker hi use karta hai. `.env` me user data nahi jata.

**Connected dikh raha hai?** Upar stats bar me `Connected 1 · Live Tokens 1` hara ho jayega. Nahi dikhe toh `Re-auth` dabao.

---

## 3. Paper Trading se Start Karo (Risk Zero)
1. `/live` pe **Go Live** ke bajaye pehle **`Paper Trading`** pe jao
2. `NIFTY` ya `BANKNIFTY` ka symbol chuno → **Quick Trade** → `Buy 1 lot` → `Paper` mode me order `FILLED` dikhega — real paisa nahi katega
3. `/positions` aur `/portfolio` pe `Paper P&L` live dekho

**Tip:** Paper pe 5-10 trades karke confidence banao, fir Live pe jao.

---

## 4. Strategy Banao — Strategy Builder (No Code)
1. `/strategies/builder` → **+ New Strategy** → `Name` + `NIFTY/BANKNIFTY` + `Weekly/Monthly` + `Entry 09:15 / Exit 15:15`
2. **Legs** jodo: `Buy CE` + `Sell PE` jaisa spread → `Lots` set karo → har leg pe `SL / Target / Trailing` laga sakte ho
3. Right me **Payoff Lab** dekho — `MAX PROFIT / MAX LOSS / Breakeven` expiry pe kya hoga, `LTP` se real premium ke saath
4. **Save** dabao → `Draft` se `Active-Paper` ban jayega → **Activity** me `Paper deploy` dikhega
5. Jo yahan banao wahi **Backtest aur Live** me same `RiskEngine` se chalega

---

## 5. Backtest Karo — Kaunsi Strategy Profitable Hai?
1. `/backtest` → `NSE:NIFTY50-INDEX | 365d | 1d | ₹1,00,000` set karo
2. **Leaderboard** tab → **Rank All 10 Now** dabao — 10 built-in `Trend Rider / MACD Cross ...` real costs ke saath chalke **net P&L se sort** hongi — `#1 👑` sabse profitable
3. `Overview` me `Equity Curve`, `Win Rate`, `Sharpe`, `Max DD` dekho; `Trades` me har trade ka `P&L / RR` aur chart pe `E/X` marker
4. Builder ki strategy backtest karni hai? Upar `Source: Builder (DSL)` chuno → apni strategy select karo → **Run**
5. Pasand aaye toh **Deploy to Paper** 1 click me — wahi strategy paper pe live chalegi

> **Real hai ya fake?** Real — `Supabase candles + Fyers/Yahoo` ke 1200+ real candles, `STT/brokerage` real rates, `Sharpe √252` — fake candles kabhi nahi bante, data na ho toh `400` error aata hai.

---

## 6. Live Trading Pe Jao (Jab Ready Ho)
1. Paper pe 1 week test ke baad `/go-live` pe jao → `PAPER | LIVE` toggle ko **LIVE** karo → `Confirm` + `daily loss` limit set karo
2. `/live` cockpit pe `Market OPEN` + `Stream live` + `Paper Equity vs Broker Margin` sab ek jagah
3. Koi bhi order `Quick Trade` ya `Terminal` se lagao — `Risk Control` (`/risk`) me `Kill Switch` hamesha ready hai — ek click me sab halt

**Risk pehle:** `/risk` pe `Max Daily Loss = ₹5000`, `Max Open Positions = 3` jaisa set karo — ye `RiskEngine` har order pe check karta hai.

---

## 7. Daily Report — Roz Shaam 18:00 IST
1. `/reports/daily` → aaj ka `Net P&L / Win Rate / Total Trades / Max DD` — `Print / Save PDF` dabake 1-pager share karo
2. Auto-send: VPS `.env` me `RESEND_API_KEY` + `TELEGRAM_BOT_TOKEN` hota hai toh roz `18:00` ko Email + Telegram pe report jata hai (cron `0 18 * * 1-5`)

---

## 8. Mobile Pe Use Karo
1. Phone pe `ai.trademetrix.tech` kholo → Browser menu → **Add to Home Screen** → `TradeMetrix` app jaisa khulega (PWA, offline shell)
2. `Push` ke liye `Settings` me Telegram link karo — `trade filled / SL hit` ka notification phone pe ayega

---

## 9. Help & Feedback
- **Help:** `/help` pe docs + video (jald)
- **Feedback:** har page ke neeche **Feedback** button → `Bug / Feature / NPS` bhejo — 12hr me reply
- **Status:** `/status` pe `API / Web / Broker Health` live

---

### Common Problems
| Problem | Fix |
|---|---|
| `Token expired — re-auth required` (red badge) | `/brokers` pe `Re-auth` dabao, OAuth allow karo |
| `No trades in backtest` | Window bada karo (365d → 5y) ya `15m` se `1d` karo; kuch strategies choppy me 0 trade deti hain — ye normal hai |
| `Order rejected: daily loss limit` | `/risk` pe limit badhao ya kal try karo |
| `Market data not available` | NIFTY/BANKNIFTY index pe try karo; futures ka Yahoo symbol nahi hota — broker feed chahiye |
| `Lemonn — API pending` | Lemonn ka public API abhi nahi hai, isliye stub hai — Fyers/Zerodha use karo |

---

**TradeMetrix Terminal © 2026 — Trading involves substantial risk. Trade responsibly. Paper pe seekho, live pe sambhal ke.**

*Ye guide `docs/USER_GUIDE.md` me bhi hai aur `/help` se linked hai. PDF chahiye toh `/reports/daily` pe Print → Save as PDF.*

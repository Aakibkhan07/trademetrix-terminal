# Trade Metrix — User Guide

## What is Trade Metrix?

Trade Metrix is an algorithmic trading platform that lets you connect your stock broker, choose a trading strategy, and automate your trades — all from one dashboard. It supports 12 Indian brokers and runs 10 proven trading strategies.

**This is algo trading software, not a "growth AI" or "psychology analysis" tool.** It executes trades based on proven technical strategies.

---

## Getting Started

### Step 1: Sign Up / Sign In

Go to **https://ai.trademetrix.tech/auth** and create an account:

- **Email + Password**: Enter your email, create a password (min 6 characters), and add your full name.
- **OTP Login**: Choose "OTP" tab, enter your email, receive a 6-digit code, and sign in without a password.
- **Google Sign-In**: If configured, click "Continue with Google" for one-click login.

After signing up, you'll be taken to the onboarding flow automatically.

### Step 2: Connect Your Broker

Go to **https://ai.trademetrix.tech/brokers** (or click "Brokers" in the sidebar).

1. Click **+ Connect Broker**.
2. Choose your broker from the list (Dhan, Upstox, Zerodha, Angel One, Fyers, Groww, 5paisa, Aliceblue, Finvasia, Flattrade, Kotak Neo, Lemonn).
3. Enter your API key and secret key from your broker's developer dashboard.
4. For OAuth brokers (Dhan, Upstox, Zerodha, Angel One), click the auth link that opens in a new tab — log into your broker and authorize Trade Metrix.
5. Click **Connect**.

Your broker will show as "Active" with a green badge.

**Where to find API keys:**
- **Zerodha**: Kite Connect → Register at https://kite.trade/ → get API key + secret
- **Dhan**: Dhan Partner → https://dhan.co/ → get client ID + secret
- **Upstox**: Upstox Developer → https://upstox.com/ → get API key + secret
- **Angel One**: Angel One API → https://angelone.in/ → get API key + secret
- **Fyers**: Fyers API → https://myfyers.com/ → get app ID + app secret

### Step 3: Check Your Funds

Go to **https://ai.trademetrix.tech/funds** to see your broker's available margin and used margin. This helps you understand how much capital you have for trading.

### Step 4: Choose a Strategy

Go to **https://ai.trademetrix.tech/strategies** to see the 10 available strategies:

| Strategy | Type | Best For |
|----------|------|----------|
| Trend Rider | Trend following | Strong directional markets |
| MACD Cross | Momentum crossover | Medium-term trends |
| Bollinger Bandit | Mean reversion | Range-bound markets |
| RSI Mean Reversion | Oscillator-based | Overextended price moves |
| ORB Pro | Opening range breakout | First 15-30 min volatility |
| SMC Sniper | Smart Money Concepts | Institutional order flow |
| Intraday Momentum | Momentum | Intraday trending days |
| Mean Reversion Pro | Statistical reversion | Mean-reverting assets |
| Breakout Scanner | Breakout detection | Consolidation breakouts |
| Arbitrage Hunter | Spread/arb | Price discrepancies |

Click on any strategy to see its details, parameters, and backtest results.

### Step 5: Backtest (Optional but Recommended)

Go to **https://ai.trademetrix.tech/backtest** to test a strategy before going live:

1. Select a strategy from the dropdown.
2. Choose the instrument (e.g., NIFTY 50, BANK NIFTY).
3. Set the time period (1 day to 5 years) and interval (1 minute to 1 day).
4. Click **Run Backtest**.
5. Review the results: total trades, win rate, net profit, max drawdown.

Backtesting uses real historical market data. If data is unavailable, the backtest will error instead of using fake data.

### Step 6: Go Live

Go to **https://ai.trademetrix.tech/go-live** to deploy a strategy:

1. **Select Broker**: Choose the broker you connected in Step 2.
2. **Select Strategy**: Choose the strategy you want to run.
3. **Select Mode**: 
   - **Paper Trading**: 가상 money — no real money at risk. Good for testing.
   - **Live Trading**: Real money — real trades on your broker account.
4. **Configure Parameters**: Set strategy-specific parameters (entry size, stop loss, etc.).
5. Click **Start**.

Your strategy will now run automatically. You can monitor it from the **Live** dashboard.

### Step 7: Monitor from the Live Dashboard

Go to **https://ai.trademetrix.tech/live** to see everything in one place:

- **Positions**: Your open positions with real-time P&L.
- **Orders**: All orders (pending, filled, cancelled).
- **Portfolio**: Your paper trading equity and broker margin.
- **Chart**: Live chart of your selected instrument.
- **Trading Controls**: Emergency stop, pause all strategies.
- **Live Signals**: Real-time strategy signals as they fire.

---

## Key Features

### Multi-Broker Support

Trade Metrix supports 12 brokers. You can connect multiple brokers at once and switch between them when deploying strategies.

**Connected brokers** show with a green "Active" badge. **Available brokers** show with a "Connect" button.

### Paper Trading

Paper trading uses virtual money (₹5L default) so you can test strategies without risking real capital. Paper trading uses the same execution engine as live trading, so results are realistic.

To start paper trading:
1. Go to **https://ai.trademetrix.tech/paper**.
2. Click **Start Paper Trading**.
3. Choose a strategy and deploy.

### Risk Controls

Go to **https://ai.trademetrix.tech/risk** to set risk guardrails:

- **Max Open Positions**: Limit the number of simultaneous positions.
- **Max Trades per Day**: Limit daily trade count.
- **Max Daily Loss**: Stop trading if daily loss exceeds a threshold.
- **Max Drawdown**: Stop trading if total drawdown exceeds a threshold.

These controls apply to both paper and live trading.

### Backtesting

Backtest any strategy against historical data before going live. Access up to 5 years of daily data or 730 days of intraday data.

### TradingView Webhook Integration

Connect TradingView alerts to Trade Metrix for automated execution:

1. Go to **https://ai.trademetrix.tech/brokers**.
2. Scroll to the "TradingView Webhook Integration" section.
3. Copy the webhook URL.
4. In TradingView, set up an alert with the webhook URL and the JSON payload format shown on the page.

### AI Assistant

Go to **https://ai.trademetrix.tech/ai** for AI-powered trading assistance — strategy recommendations, market analysis, and trade ideas.

---

## Troubleshooting

### Broker Connection Issues

- **"Not authenticated" error**: Sign in first, then try connecting a broker.
- **OAuth link doesn't open**: Check your browser's pop-up blocker. Allow pop-ups for ai.trademetrix.tech.
- **Token expired**: Re-auth the broker from the Brokers page (click "Re-auth" on the broker card).
- **Invalid API keys**: Double-check your API key and secret from your broker's developer dashboard. Make sure you're using the correct keys for the correct environment (test vs live).

### Strategy Not Starting

- **"No broker connected"**: Connect at least one broker first (Step 2).
- **"No strategy selected"**: Choose a strategy in the Go Live wizard.
- **Backtest errors**: Make sure the instrument symbol is correct (e.g., "NIFTY50-INDEX" for NIFTY 50). Try a shorter time period if data is unavailable.

### Market Data Not Loading

- Market data is only available during market hours (9:15 AM – 3:30 PM IST, Monday–Saturday).
- Check the market status on the Live dashboard — it shows "MARKET OPEN" or "MARKET CLOSED".
- If the market is open but data isn't loading, try refreshing the page or reconnecting your broker.

### Page Shows 500 Error

- Refresh the page.
- Sign out and sign back in.
- Clear your browser cache and cookies.
- If the issue persists, contact support.

---

## Safety Notes

- **Start with paper trading** before using live money.
- **Start small** — use minimal position sizes when going live for the first time.
- **Monitor your strategies** — check the Live dashboard regularly.
- **Use risk controls** — set max loss and drawdown limits.
- **API keys are encrypted** — your broker credentials are stored securely on the server.
- **You are responsible for your trades** — Trade Metrix executes strategies automatically, but you control which strategies to run and when to stop them.

---

## Support

- **Help Page**: https://ai.trademetrix.tech/help
- **Settings**: https://ai.trademetrix.tech/settings (manage your account, connected brokers, notifications)
- **Analytics**: https://ai.trademetrix.tech/analytics (view your trading performance)

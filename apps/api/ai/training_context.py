STRATEGY_RECOMMENDATIONS = """STRATEGY RECOMMENDATIONS (capital & risk based):

By Capital:
• **₹0-₹10,000**: Free plan, paper trading. Recommended: Intraday Momentum, Trend Rider
• **₹10,000-₹50,000**: Monthly plan suggested. Recommended: VWAP Band, RSI Mean Reversion, Gap Up Express
• **₹50,000-₹2,00,000**: Quarterly or Half-Yearly. Pro strategies: Bollinger Bandit, ORB Pro, Trend Rider Buyer
• **₹2,00,000+**: Half-Yearly or Yearly. Enterprise: SMC Sniper, Expiry Hunter, Option Wheel

By Style:
• **Scalping (1-5 min)**: Intraday Momentum, VWAP Band, Breakout Scanner
• **Intraday (5 min - EOD)**: Trend Rider, MACD Cross, Gap Up Express
• **Swing (1-5 days)**: RSI Mean Reversion, Bollinger Bandit, Mean Reversion Pro
• **Options Buying**: Momentum Breakout Buyer, Trend Rider Buyer, Long Straddle
• **Options Selling/Wheel**: Expiry Hunter, Option Wheel
• **Automated/Algo**: Graph Strategy (Strategy Builder), Arbitrage Hunter
• **Beginners**: Intraday Momentum (easiest), Trend Rider (simple EMA crossover)
• **Advanced**: SMC Sniper, Arbitrage Hunter, Option Wheel

By Risk Tolerance:
• **Low Risk**: RSI Mean Reversion, VWAP Band, Option Wheel — defined risk, high win rate
• **Medium Risk**: Trend Rider, MACD Cross, Bollinger Bandit — trending markets with stoploss
• **High Risk**: Long Straddle, Momentum Breakout Buyer, Expiry Hunter — options strategies

Strategy Details:
• **Trend Rider (Free)**: EMA9/21 crossover with ADX filter. Best for trending markets. TF: 15min-1hr
• **MACD Cross (Free)**: MACD line/signal crossover. Works in range-bound markets. TF: 15min-1hr
• **Intraday Momentum (Free)**: VWAP cross + RSI divergence + volume thrust. Fast scalper. TF: 1-5min
• **VWAP Band (Starter)**: VWAP-based mean reversion with volatility bands. TF: 5-15min
• **RSI Mean Reversion (Starter)**: RSI overbought/oversold with trend filter. TF: 15min-1hr
• **Momentum Breakout Buyer (Starter)**: OR breakout + volume + premium management. Options buyer.
• **Gap Up Express (Starter)**: Pre-market gap + volume spike. First 30min of market.
• **Bollinger Bandit (Pro)**: BB squeeze + Keltner channel confluence. TF: 15min-1hr
• **ORB Pro (Pro)**: Opening range breakout with volume. TF: 5-15min
• **Trend Rider Buyer (Pro)**: Trend Rider + options buying logic. Premium management included.
• **Mean Reversion Pro (Pro)**: Multi-indicator mean reversion + volume profile. TF: 5-15min
• **Breakout Scanner (Pro)**: Real-time consolidation breakout scanner across multiple timeframes.
• **Graph Strategy (Pro)**: Drag-drop visual strategy builder. Create custom strategies.
• **SMC Sniper (Enterprise)**: Smart Money Concepts — order blocks, liquidity grabs, FVG.
• **Expiry Hunter (Enterprise)**: Weekly expiry theta decay + gamma scalping. F&O only.
• **Long Straddle (Enterprise)**: ATM CE+PE buy for volatility expansion with IV gate.
• **Option Wheel (Enterprise)**: Cash-secured puts + covered calls. Consistent premium collection.
• **Arbitrage Hunter (Enterprise)**: Statistical arbitrage, z-score divergence, pair trading."""

PSYCHOLOGY_COACH = """TRADING PSYCHOLOGY COACHING:

Common Issues & How to Help:
1. **Loss recovery / revenge trading**: "Loss ke baad market mein wapas koodna galat hai. Ruko, analyze karo kya galat hua. Paper trading pe practice karo phir wapas aao."
2. **FOMO (fear of missing out)**: "Koi trade miss karna loss nahi hai. Market kal bhi khulega. Discipline > Opportunity."
3. **Overtrading**: "Din mein 10-15 trades? Quality > Quantity. Sirf setup milne pe trade karo, boredom se nahi."
4. **Not taking stoploss**: "Stoploss lagana ego ki baat nahi hai — capital bachane ki hai. Har trade mein stoploss rakho."
5. **Holding losers too long**: "Loss ko 'investment' mat banao. Agar stoploss hit hai toh nikal jao. Capital bachao next trade ke liye."
6. **Booking profits too early**: "Runner ko jaane do. Trailing stoploss use karo taaki trend ka poora fayda utha sako."
7. **Overconfidence after wins**: "Lagatar 5 winning trades ke baad bhi discipline mat todo. Market aapko humble kar degi."
8. **Analysis paralysis**: "Perfect setup ka wait karte karte din nikal jaata hai. 80% setup milte hi trade karo, perfect ka wait mat karo."

Discipline Rules:
• Risk per trade: 1-2% of capital max
• Daily loss limit: Stop trading if hit — go back tomorrow
• Win rate ≠ Profitability: 40% win rate with 3:1 RR can be profitable
• Journal every trade: Entry reason, exit reason, emotion before trade
• No trading: After 3 consecutive losses, after big personal events, when sick/tired
• Review: Weekly review of all trades — find patterns in mistakes"""

PLATFORM_TUTORIAL = """PLATFORM FEATURE WALKTHROUGH:

1. **Dashboard** (/dashboard): Main hub. See all your strategies running, positions, PnL in real-time.
2. **Admin Tab**: Only for admins. Manage users, tiers, place trades for users, view all orders.
3. **Trade Router**: Place manual trades — select broker, symbol, quantity, side. Unified search for symbols.
4. **Strategies Catalog** (/strategies/catalog): Browse all 18+ strategies with their required tier.
5. **Strategy Builder** (Graph Strategy): Visual drag-drop builder. Blocks: Entry, Exit, Filter, Risk, Logic.
6. **Backtesting**: Test any strategy on historical data. Monthly plan = 1yr, Yearly = 5yr data.
7. **Risk Settings**: Set max daily loss, kill switch, enable/disable live trading, broker connections.
8. **AI Copilot**: You're talking to it right now! Ask anything about your account, strategies, market.
9. **AI Desk** (/ai/desk): Execute commands like "square off all", "pause strategy X", "show positions".
10. **AI Journal** (/ai/journal): Automated trade journal with psychological analysis and discipline score.
11. **Pricing** (/pricing): View all plans, features comparison, subscribe via Razorpay.
12. **Subscriptions**: Manage your current plan, upgrade, cancel. Razorpay handles payments.
13. **Search Bar**: Universal search — type a stock/index name, see CE/PE prices with %, click Buy.

Common Tasks:
• "How to start a strategy?" → Go to Strategies Catalog → Pick one → Configure parameters → Assign to broker
• "How to connect my broker?" → Admin handles broker credentials. Contact support.
• "Strategy not running?" → Check risk settings → Check broker is connected → Check daily loss not hit
• "How to backtest?" → Go to strategy → Backtest tab → Select date range → Run
• "How to create my own strategy?" → Graph Strategy (Half-Yearly+) → Drag-drop blocks → Save → Deploy"""

COMPETITOR_EDGE = '''COMPETITOR COMPARISON:

| Feature | TradeMetrix | Zerodha Streak | Angel One | Dhan | Upstox |
|---------|------------|----------------|-----------|------|--------|
| Strategy Automation | ✅ AI-Powered | ✅ Basic | ❌ No | ❌ No | ❌ No |
| AI Copilot | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| Multi-Broker | ✅ 7 brokers | ❌ Only Zerodha | ❌ Only Angel | ❌ Only Dhan | ❌ Only Upstox |
| Risk Management | ✅ Real-time | ❌ Basic | ❌ No | ❌ No | ❌ No |
| Backtesting | ✅ 1-5yr data | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Strategy Builder | ✅ Visual drag-drop | ❌ Code only | ❌ No | ❌ No | ❌ No |
| Options Strategies | ✅ 7+ | ❌ Limited | ❌ No | ❌ No | ❌ No |
| Auto Square-off | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| Trailing SL | ✅ Yes | ✅ Basic | ✅ Basic | ❌ No | ✅ Basic |
| Indian Support | ✅ 24/7 WhatsApp | ❌ Email only | ❌ Call center | ❌ Email | ❌ Email |
| AI Trade Journal | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |

Key Differentiators:
• **TradeMetrix ek platform hai — competitors sirf brokerage**: Hum sirf trade nahi karate, pura ecosystem dete hain
• **AI-powered**: Copilot, Desk, Journal — teeno AI-based hai. Kisi competitor ke paas nahi hai
• **Multi-broker**: Ek hi platform se Angel, Zerodha, Fyers, Dhan, Upstox sab pe trade karo
• **Risk Management**: Real-time drawdown control, daily loss limits, kill switch — professional grade
• **Strategy Builder**: Visual drag-drop, koi coding nahi chahiye. Competitors mein sirf Streak hai (coding required)
• **Options Focus**: 7+ options-specific strategies — Expiry Hunter, Option Wheel, Long Straddle, etc.

When User Compares:
• If they mention "Zerodha sasta hai" → "Zerodha sirf brokerage platform hai. Unke paas AI assistant, risk management, multi-broker support nahi hai. Aap ek platform mein sab kuch le rahe ho."
• If they mention "Streak already hai" → "Streak mein sirf basic Algo trading hai, wo bhi Zerodha ke saath. TradeMetrix mein 7 brokers + AI + Risk Manager + Strategy Builder sab ek saath hai."
• If they mention "Angel One free deta hai" → "Free ka matlab hai aap product ho. Angel One brokerage se paisa banata hai. TradeMetrix aapko trader banata hai — strategies, risk management, AI assistance ke saath."'''

BUILDER_GUIDE = '''STRATEGY BUILDER (Graph Strategy) GUIDE:

Available Blocks:
• **Entry Blocks**: EMA crossover, RSI cross, Price breakout, VWAP touch, Volume spike, Time-based
• **Exit Blocks**: Trailing SL, Fixed target, RSI overbought/oversold, Time exit, Candle pattern
• **Filter Blocks**: ADF trend filter, Volume filter, Volatility filter, Time filter, Day filter
• **Logic Blocks**: AND, OR, NOT, Compare (>, <, =), Counter, Timer
• **Risk Blocks**: Position size calculator, Max loss guard, Correlation filter

How to Build:
1. Drag Entry block → set condition (e.g., EMA9 crosses above EMA21)
2. Drag Filter block → connect to Entry (e.g., ADX > 25 for trending market)
3. Drag Exit block → set target/stoploss (e.g., Trailing SL at 2 ATR)
4. Drag Risk block → set position size (% of capital)
5. Connect all blocks → Name your strategy → Save → Deploy to broker

Example: Simple EMA Crossover
   [Entry: EMA9 crossover EMA21] → [Filter: ADX > 25] → [Exit: Trailing SL 1.5%] → [Risk: 2% per trade]

Common Patterns:
• Trend Following: Entry(breakout) + Filter(ADX trend) + Exit(trailing SL)
• Mean Reversion: Entry(RSI oversold) + Filter(volume spike) + Exit(fixed target at VWAP)
• Scalping: Entry(VWAP cross) + Filter(volume > avg) + Exit(time-based 5min)
• Options: Entry(breakout) + Filter(IV percentile) + Exit(premium-based)

Tips:
• Less is more: 3-4 blocks is enough. Complex strategies overfit.
• Always use a risk block: Never deploy without position sizing.
• Backtest first: Run on 6 months data before going live.
• Start simple: Get a working simple strategy first, then add complexity.'''

MARKET_EDUCATION = """MARKET EDUCATION (F&O Focus):

Option Greeks Simplified:
• **Delta (-1 to +1)**: How much option price moves when underlying moves ₹1. CE=positive, PE=negative.
  - ATM ~0.5, ITM ~0.7-0.9, OTM ~0.1-0.3
• **Gamma**: Rate of change of delta. High near expiry. ATM options have highest gamma.
• **Theta (Time Decay)**: Daily option premium decay. -ve for buyers, +ve for sellers. Accelerates near expiry.
• **Vega**: Sensitivity to volatility. High when IV is high. Important during events/budget.
• **IV (Implied Volatility)**: Market's expectation of future volatility. High IV = expensive options.

Expiry Day Tips:
• Last 1 hour: Gamma risk is extreme. Positions can swing wildly.
• Theta decay accelerates: 70% of decay happens in last 3 days.
• Straddle/Strangle sellers: High probability but tail risk.
• Recommended: Don't take new positions after 2 PM on expiry day.

F&O Terms:
• **ATM/ITM/OTM**: At-the-money (strike≈spot), In-the-money, Out-of-the-money
• **Premium**: Price of the option contract (quoted per share, multiply by lot size)
• **Lot Size**: Nifty=25, Bank Nifty=15, Fin Nifty=40, Sensex=10
• **Margin**: Amount blocked for selling options (varies by broker, volatility)
• **SPAN/Exposure**: Initial margin + additional margin for option sellers
• **Max Pain**: Strike where most option buyers lose money — price often gravitates here near expiry
• **OI (Open Interest)**: Total outstanding contracts. Increasing OI = trend confirmation

Risk Management Rules:
• Never risk more than 1-2% of capital per trade
• Option Buying: Defined risk (premium paid), low probability
• Option Selling: High probability, unlimited risk (use stoploss)
• Position Sizing: Lot size × premium × number of lots
• Daily Loss: Stop trading if ₹2,000 loss (Free) / ₹5,000 (Pro) / ₹10,000 (Enterprise)
• Correlation: Don't take opposite positions in highly correlated indices (Nifty + BankNifty)

Indices Info:
• **Nifty 50**: 50 stocks, ~1 point = ₹25 (F&O lot size 25)
• **Bank Nifty**: Banking stocks, ~1 point = ₹15 (F&O lot size 15)
• **Fin Nifty**: Financial services, ~1 point = ₹40 (F&O lot size 40)
• **Sensex**: 30 stocks, no F&O (only cash market)
• Market Hours: 9:15 AM - 3:30 PM (Mon-Fri), Pre-market: 9:00-9:15 AM
• Settlement: Weekly expiry (Thu-Fri depending on index)"""

TRAINING_CONTEXT = f"""
========== STRATEGY RECOMMENDATIONS ==========

{STRATEGY_RECOMMENDATIONS}

========== TRADING PSYCHOLOGY COACH ==========

{PSYCHOLOGY_COACH}

========== PLATFORM TUTORIAL ==========

{PLATFORM_TUTORIAL}

========== COMPETITOR EDGE ==========

{COMPETITOR_EDGE}

========== STRATEGY BUILDER GUIDE ==========

{BUILDER_GUIDE}

========== MARKET EDUCATION ==========

{MARKET_EDUCATION}
"""

def get_training_context() -> str:
    return TRAINING_CONTEXT

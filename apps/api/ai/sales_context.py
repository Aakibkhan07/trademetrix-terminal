PLANS_DISPLAY = """TRADEMETRIX PRICING PLANS (Indian Users — ₹):

| Plan | Price | Best For |
|------|-------|----------|
| Free | ₹0 | Paper trading, learning, 1 strategy |
| Monthly | ₹15,500/mo | Trial, short-term, live trading |
| Quarterly | ₹35,500 (₹11,833/mo) | Medium-term, saves ₹10,999 |
| Half-Yearly ⭐ | ₹69,500 (₹11,583/mo) | Best value, saves ₹23,500 |
| Yearly | ₹1,25,000 (₹10,416/mo) | Serious traders, saves ₹61,000 |"""

FEATURES_BY_TIER = """FEATURES PER TIER:

• **Free**: 1 strategy, paper trading only, ₹2,000 daily loss cap, no backtesting
• **Monthly**: 2 strategies, live trading, backtesting 1yr, strategy builder, 1 broker, email support
• **Quarterly**: 4 strategies, trailing SL, backtesting 2yr, 3 brokers, ₹3,000 daily loss, priority email
• **Half-Yearly**: 8 strategies, re-entry/square-off, strategy builder beta, backtesting 5yr, all 7 brokers, 24/7 WhatsApp, ₹5,000 daily loss
• **Yearly**: 15 strategies, custom strategy dev, dedicated manager, full platform access, ₹10,000 daily loss, 24/7 priority support"""

STRATEGY_ACCESS = """STRATEGIES LOCKED BEHIND TIERS:

Free (2): Trend Rider, MACD Cross, Intraday Momentum
Starter/Monthly (5): +VWAP Band, RSI Mean Reversion, Momentum Breakout Buyer, Gap Up Express
Pro/Half-Yearly (5): +Bollinger Bandit, ORB Pro, Trend Rider Buyer, Mean Reversion Pro, Breakout Scanner, Graph Strategy
Enterprise/Yearly (4): +SMC Sniper, Expiry Hunter, Long Straddle, Option Wheel, Arbitrage Hunter"""

UPSELL_TRIGGERS = """UPSELL OPPORTUNITIES — what to suggest when user shows these signals:

1. **Strategy limit hit**: "You're on Free (1 strategy max). Upgrading unlocks more strategies + live trading."
   → Suggest Monthly (₹15,500) or best-value Half-Yearly (₹69,500)

2. **Wants live trading on free**: "Live trading requires a paid plan. Monthly starts at ₹15,500."
   → Suggest Monthly as entry point

3. **Wants more brokers**: "Free supports 1 broker. Higher tiers support 3 to all 7 brokers."

4. **Hits ₹2,000 daily loss limit**: "Increasing your daily loss cap requires upgrading."
   → Quarterly gives ₹3,000, Half-Yearly gives ₹5,000

5. **Asks about trailing SL**: "Trailing stop-loss is available from Quarterly plan onwards."

6. **Wants strategy builder**: "The visual strategy builder is available from Half-Yearly plan."

7. **Wants backtesting**: "Backtesting is available from Monthly (1yr) up to Yearly (5yr)."

8. **Wants custom strategy**: "Custom strategy development is only on the Yearly plan."

9. **Compares plans or asks "which plan?"**: Recommend Half-Yearly as best value / most popular.

10. **Mentions budget concern**: Break down to per-day cost: Monthly ≈ ₹517/day, Half-Yearly ≈ ₹386/day
    Compare to what they'd lose in a single bad trade without proper risk management."""

OBJECTION_HANDLING = '''OBJECTION HANDLING SCRIPTS:

Q: "Bahut mehnga hai / Too expensive"
A: "Sir, ek hi trade mein aap ₹5,000-10,000 loss kar sakte hain bina proper system ke. Hamara platform risk management ke saath aata hai jo aapki capital bachata hai. Half-Yearly sirf ₹386/day hai — ek chai aur nashte se bhi sasta."

Q: "Free plan kaafi hai"
A: "Free plan sirf paper trading ke liye hai. Live trading, backtesting, aur advanced strategies ke liye aapko upgrade karna hoga. Kya aap live trading try karna chahenge?"

Q: "I\'ll think about it"
A: "Ji, samajh gaya. Lekin yeh limited time pricing hai. Abhi subscribe karte hain toh aap 1 din ka free trial bhi pa sakte hain. Kya main aapko trial activate kar doon?"

Q: "Dusre platform saste hain"
A: "Hum sirf trading platform nahi hai — AI-powered assistant, real-time risk management, aur multi-broker support ke saath ek complete ecosystem hai. Aapko alag se kuch nahi lena padega."

Q: "Market mein loss ho raha hai, abhi invest nahi kar sakta"
A: "Exactly isiliye aapko TradeMetrix ki zaroorat hai. Hamari strategies risk-managed hoti hain. Paper trading se shuru karein, phir jab confident ho to live trading pe aayein."

Q: "Does it really work?"
A: "Haan. Real data pe backtested strategies hai. Aap demo dekhna chahenge? Main koi bhi strategy ka performance dikha sakta hoon."'''

SALES_CONTEXT = f"""
=== PRICING & SALES KNOWLEDGE ===

{PLANS_DISPLAY}

{FEATURES_BY_TIER}

{STRATEGY_ACCESS}

{UPSELL_TRIGGERS}

{OBJECTION_HANDLING}
"""

def get_sales_context() -> str:
    return SALES_CONTEXT

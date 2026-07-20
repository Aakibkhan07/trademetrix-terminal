PLANS_DISPLAY = """TRADEMETRIX PRICING PLANS (₹):

| Plan | Price | Per Day Cost | Best For |
|------|-------|-------------|----------|
| Free | ₹0 | ₹0 | Paper trading, learning, 1 strategy |
| Monthly | ₹15,500/mo | ~₹517/day | Trial, short-term, live trading |
| Quarterly | ₹35,500 (₹11,833/mo) | ~₹394/day | Medium-term, saves ₹10,999 |
| Half-Yearly ⭐ | ₹69,500 (₹11,583/mo) | ~₹386/day | Best value, saves ₹23,500 |
| Yearly | ₹1,25,000 (₹10,416/mo) | ~₹342/day | Serious traders, saves ₹61,000 |"""

FEATURES_BY_TIER = """FEATURES PER TIER:

• **Free**: 1 strategy, paper trading only, ₹2,000 daily loss cap, no backtesting, no live trading
• **Monthly**: 2 strategies, live trading (NSE/BSE F&O), backtesting 1yr, strategy builder, 1 broker, email support
• **Quarterly**: 4 strategies, trailing SL, backtesting 2yr, 3 brokers, ₹3,000 daily loss, priority email
• **Half-Yearly**: 8 strategies, re-entry/square-off, strategy builder, backtesting 5yr, all 7 brokers, 24/7 WhatsApp, ₹5,000 daily loss
• **Yearly**: 15 strategies, custom strategy dev, dedicated manager, full platform access, ₹10,000 daily loss, 24/7 priority support"""

STRATEGY_ACCESS = """STRATEGIES LOCKED BEHIND TIERS:

Free (3): Trend Rider, MACD Cross, Intraday Momentum
Monthly/Starter (5): +VWAP Band, RSI Mean Reversion, Momentum Breakout Buyer, Gap Up Express
Half-Yearly/Pro (6): +Bollinger Bandit, ORB Pro, Trend Rider Buyer, Mean Reversion Pro, Breakout Scanner, Graph Strategy
Yearly/Enterprise (5): +SMC Sniper, Expiry Hunter, Long Straddle, Option Wheel, Arbitrage Hunter"""

UPSELL_TRIGGERS = '''UPSELL OPPORTUNITIES (Indian Context):

0. **Discount/coupon maange**: "Ji haan, discount available hai! Sirf Yearly plan (₹1,25,000) pe. Already ₹61,000 bachata hai plus extra discount. Kya main quote nikalwa doon?"
   → First upsell to Yearly with discount. If budget issue, suggest Half-Yearly as best value or free trial.

1. **Strategy limit hit**: "Aap Free plan pe ho jahan sirf 1 strategy allowed hai. Upgrade karke aap multiple strategies ek saath chala sakte ho."
   → Suggest Monthly (₹15,500) ya best-value Half-Yearly (₹69,500)

2. **Wants live trading on free**: "Free plan sirf paper trading ke liye hai. Live trading Monthly ₹15,500 se start hota hai. Pehle free trial lo."
   → Suggest Monthly as entry point

3. **Wants more brokers**: "Free sirf 1 broker deta hai. Higher tiers mein 3 se lekar saare 7 brokers milte hain — Angel, Zerodha, Fyers, etc."

4. **Hits ₹2,000 daily loss limit**: "Daily loss limit badhana hai toh upgrade karo. Quarterly ₹3,000 deta hai, Half-Yearly ₹5,000."

5. **Asks about trailing SL**: "Trailing SL Quarterly plan se available hai."

6. **Wants strategy builder**: "Visual strategy builder Half-Yearly plan se milta hai."

7. **Wants backtesting**: "Backtesting Monthly se start (1yr) hai, Yearly tak 5yr ka data milta hai."

8. **Wants custom strategy**: "Custom strategy development sirf Yearly plan mein."

9. **Compares plans**: Always recommend Half-Yearly as best value. 8 strategies, 5yr backtest, all brokers, 24/7 WhatsApp support.

10. **Budget concern**: "Monthly sirf ₹517/day — ek sutta aur chai se bhi sasta. Half-Yearly ₹386/day. Socho, ek galat trade mein aap ₹5,000-10,000 gawa dete ho. Yeh platform aapko wo loss bachata hai."'''

OBJECTION_HANDLING = '''OBJECTION HANDLING (Indian audience ke liye):

Q: "Bahut mehnga hai / Too expensive — ₹15,500 bohot zyada hai"
A: "Sir, aap sahi keh rahe ho. Lekin ek baar sochiye — agar aap bina system ke ek option buy karte ho aur loss karte ho, toh ₹15,000-20,000 udd jaate hain. TradeMetrix ka risk-managed approach aapki capital bachata hai. Monthly sirf ₹517/day hai — yeh aapki chai-sutta aur petrol se bhi sasta hai. Aur agar aap Half-Yearly lete ho toh sirf ₹386/day. Kya main aapko 1 din ka free trial activate kar doon?"

Q: "Free plan kaafi hai mere liye"
A: "Free plan achha hai paper trading seekhne ke liye. Lekin agar aap real money se live trading karna chahte ho, backtesting karni hai, ya advanced strategies use karni hain toh upgrade karna padega. Kya aapko live trading mein interest hai? Koi specific strategy hai jo aap try karna chahte ho?"

Q: "Mujhe F&O ka experience nahi hai, pehle seekhna hoga"
A: "Bilkul! TradeMetrix iske liye perfect hai. Aap Free plan pe paper trading se shuru kar sakte ho bina paisa lagaye. Phir jab confident ho, toh live trading pe upgrade kar lo. Hamari strategies risk-managed hain — aap bina jyada loss kiye trade karna seekh sakte ho."

Q: "I\'ll think about it / Soch ke batata hoon"
A: "Ji, samajh gaya. Lekin limited period ka free trial available hai. Aaj hi activate karte hain toh aap 1 din free premium features try kar sakte ho. Phir agar pasand aaye toh continue karna. Kya main activate kar doon?"

Q: "Dusre platform saste hain / Angel One free deta hai"
A: "Angel One, Zerodha jaise platform sirf brokerage platform hain. TradeMetrix ek complete AI-powered trading ecosystem hai — aapko alag se strategy builder, risk management, AI assistant, backtesting, aur multi-broker support milta hai ek hi jagah. Woh log sirf trade execute karte hain, hum aapko trade ka poora system dete hain."

Q: "Market mein loss ho raha hai, abhi kuch nahi le sakta"
A: "Bilkul samajh sakta hoon. Market mein loss hona common hai — isiliye aapko ek system ki zaroorat hai. Paper trading se shuru karein free mein. Strategies ko backtest karein bina paisa lagaye. Phir jab confident ho, live trading karein. TradeMetrix ki risk management aapki capital ko bachati hai."

Q: "Telegram tips / stock groups se kaam chal raha hai"
A: "Sir, Telegram tips pe bharosa karke aapne kitna loss kiya hai sochiye. TradeMetrix data-driven, backtested strategies deta hai — kisi ke random tips nahi. Aur aap profit booking, stoploss, risk management sab automate kar sakte ho."

Q: "Options buying mein sab kuch uda diya, ab darr lagta hai"
A: "Options buying risky hai — isiliye TradeMetrix ka strategy builder re-entry aur square-off allow karta hai. Aap defined risk ke saath trade kar sakte ho. Pehle paper trading se confidence build karein."

Q: "ITR / tax document nahi hai, payment kaise karunga?"
A: "Payment ke liye kisi tax document ki zaroorat nahi hai. Aap credit card, debit card, UPI, net banking — jo bhi ho, use kar sakte ho. Razorpay se secure payment hota hai."

Q: "Does it really work? Pakka chalega?"
A: "Haan. Humari strategies real market data pe backtested hain. Demo dekhna chahenge? Main koi bhi strategy ka performance dikha sakta hoon — kitne trades, win rate, profit factor sab dikhega."

Q: "Discount / coupon code hai kya? Koi offer?"
A: "Ji haan, discount available hai! Lekin wo sirf Yearly plan (₹1,25,000) pe milta hai. Yearly plan already ₹61,000 bachata hai monthly rate se, aur uske upar extra bhi discount lag jaata hai. Kya main aapke liye Yearly plan ka discounted quote nikalwa doon? Warna aap pehle free trial se start kar sakte ho."'''

INDIAN_PSYCHOLOGY = """INDIAN TRADER PSYCHOLOGY — understand your audience:

• **F&O addiction**: Most Indian users are obsessed with Bank Nifty, Nifty options, expiry day trading. They love the "lottery" feeling of options buying.
• **Loss recovery mindset**: "Jo loss hua hai wo wapas laana hai" — they chase losses. Pitch risk management as their savior.
• **Jugaad mentality**: They want maximum features at minimum price. Show value (₹/day) not just total price.
• **"Mera dost use karta hai"**: Social proof matters. Mention "1000+ Indian traders".
• **Trust deficit**: Indian traders have been cheated by Telegram tips, fake gurus. Build trust — mention SEBI compliance, data security, Indian company.
• **"Ghar wale nahi maanenge"**: If they're investing significant money, family approval matters.
• **Intraday focus**: Most Indian traders want intraday/BTST/F&O strategies. Scalping is huge.
• **"Time nahi hai"**: Many are salaried professionals who want automated trading — sell the "set it and forget it" angle.
• **Hinglish comfort**: Mix Hindi and English naturally. Pure Hindi sounds fake. Pure English sounds like a sales call center.
• **Respect elders**: Use "Sir" or "Ji" even with younger users. Politeness matters in Indian culture."""

SALES_CONTEXT = f"""
========== SALES & PRICING KNOWLEDGE ==========

{PLANS_DISPLAY}

{FEATURES_BY_TIER}

{STRATEGY_ACCESS}

{UPSELL_TRIGGERS}

{OBJECTION_HANDLING}

{INDIAN_PSYCHOLOGY}
"""

def get_sales_context() -> str:
    return SALES_CONTEXT

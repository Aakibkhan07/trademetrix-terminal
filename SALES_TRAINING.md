# TradeMetrix Terminal — Sales Training Guide

---

## Part 1: Project Summary (प्रोजेक्ट का परिचय)

### क्या है TradeMetrix Terminal?
TradeMetrix Terminal एक **अल्गोरिदमिक ट्रेडिंग प्लेटफॉर्म** है — एक ऑल-इन-वन सिस्टम जो शेयर बाजार में ऑटोमेटेड ट्रेडिंग करता है। यह सिर्फ एक सॉफ्टवेयर नहीं, बल्कि एक पूरा **ट्रेडिंग ऑपरेटिंग सिस्टम** है।

### Tech Stack
- **Frontend:** Next.js 14 (React, TypeScript) — आधुनिक, तेज, responsive
- **Backend:** FastAPI (Python 3.12) — शक्तिशाली, low-latency
- **Database:** Supabase (PostgreSQL) — cloud-based, real-time
- **AI:** Google Gemini / OpenRouter — AI Copilot, AI Desk, Trade Journal
- **Infrastructure:** Docker, VPS, Nginx, Redis, Prometheus, Grafana

### Core Features
| Feature | Description |
|---------|------------|
| **10 Brokers** | Fyers, Angel One, Zerodha, Dhan, Upstox, Alice Blue, 5Paisa, Finvasia, Flattrade, Kotak + Paper Trading |
| **17 Strategies** | Trend Rider, Momentum, MACD, VWAP, RSI, Bollinger, ORB, SMC, Straddle, Option Wheel, Expiry Hunter + more |
| **Visual Builder** | Block-based drag-drop strategy builder — कोडिंग की ज़रूरत नहीं |
| **AI Assistant** | Natural language commands, trade journal analysis, contextual copilot |
| **Risk Management** | 16+ risk rules, kill switch, daily loss limits, max position size |
| **Option Chain** | Real-time CE/PE chain with PCR, Max Pain, OI change tracking |
| **Backtesting** | Historical + tick-by-tick replay engine |
| **Admin Panel** | User management, trade placement, broadcast, audit logs |
| **Paper Trading** | Virtual broker with ₹1Cr simulated capital |

---

## Part 2: Usage Guide — Software kaise use karein

### A. Users के लिए (ट्रेडर्स)

#### 1. Account Setup
```
www.trademetrix.tech → Sign Up → Email/OTP Register → Onboarding Wizard
```
- Email/password या OTP से रजिस्टर करें
- Onboarding wizard आपको step-by-step guide करेगा
- Subscription चुनें (Monthly ₹15,500 / Quarterly ₹35,500 / Half-Yearly ₹69,500 / Yearly ₹1,25,000)

#### 2. Broker Connect
```
Dashboard → Brokers → Add Broker → Choose your broker → Authenticate
```
- 10 brokers में से अपना broker चुनें
- OAuth या credentials से कनेक्ट करें
- Paper trading से शुरू करें (₹1Cr virtual capital)

#### 3. Strategy Selection
```
Strategies → Catalog → Browse → Assign
```
- **Free tier:** Trend Rider, Intraday Momentum, MACD Cross
- **Starter tier:** VWAP Band, RSI Mean Reversion, Gap Up Express + Momentum Breakout Buyer
- **Pro tier:** Bollinger Bandit, ORB Pro, Trend Rider Buyer, Mean Reversion Pro, Breakout Scanner
- **Enterprise:** SMC Sniper, Expiry Hunter, Long Straddle, Option Wheel, Arbitrage Hunter

#### 4. Visual Strategy Builder (कोडिंग नहीं आती? कोई बात नहीं!)
```
Terminal → Builder → Drag & Drop blocks → Configure → Deploy
```
- Blocks को drag करके strategy बनाएं
- Indicators चुनें (EMA, RSI, MACD, VWAP, Bollinger, etc.)
- Entry/Exit conditions set करें
- Risk parameters configure करें
- एक क्लिक में deploy करें

#### 5. Manual Trading
```
Trade → Search Symbol → Select Strike → CE/PE → Buy/Sell
```
- Universal search bar — symbol या strike price type करें
- Real-time option chain देखें
- CE/PE prices with % change दिखता है
- एक क्लिक में trade place करें

#### 6. AI Features
```
AI Desk     → "Show my positions" / "Square off all"
AI Copilot  → "Why was my order rejected?" / "How is my P&L today?"
Journal     → AI analyzes your trading behavior, gives score 1-100
```

#### 7. Risk Management
```
Risk Dashboard → Set limits → Enable Kill Switch
```
- Daily loss limit set करें (Free: ₹2K, Enterprise: ₹10K+)
- Max position size, max exposure, max drawdown
- Kill switch — emergency stop, एक क्लिक में सब बंद
- PAPER vs LIVE mode — LIVE के लिए explicit opt-in ज़रूरी

#### 8. Monitoring
```
Dashboard     → Portfolio summary, P&L, positions
Analytics     → Charts and metrics
Positions     → Current open positions
Orders        → Order history with notes
```

### B. Admin के लिए (आप — सर्विस प्रोवाइडर)

#### Access
```
https://ai.trademetrix.tech/admin
```
#### Features
| Tab | क्या कर सकते हैं |
|-----|------------------|
| **Dashboard** | Total users, admins, assignments, tier distribution |
| **Users** | List users, update subscription tier |
| **Strategies** | Assign strategies to users, bulk assign, import/export |
| **Brokers** | View/validate/re-auth broker credentials |
| **Trades** | Execute trades on behalf of users, browse all orders |
| **Broadcast** | Send trade signals to all users, email notifications |
| **Audit** | Filterable event history |
| **Risk** | All users' risk settings at one place |
| **Founder** | 11-section metrics dashboard |

#### Admin Trade Placement
```
Admin → Trades → Select User → Search Strike → Buy CE/PE
```
- किसी भी user की तरफ से trade place कर सकते हैं
- Market closed होने पर भी admin trades work करती हैं

---

## Part 3: Sales Pitch — हिंग्लिश में

### 3-Minute Elevator Pitch

> "भाई साहब, आप शेयर बाजार में ट्रेड करते हैं? हाथ से ट्रेड करते हो या फिर आपको ऑटोमेशन चाहिए?

> TradeMetrix Terminal एक अल्गोरिदमिक ट्रेडिंग प्लेटफॉर्म है — मतलब आपकी तरफ से रोबोट ट्रेड करेगा। ना भाव देखना, ना tension, ना emotional trading.

> **क्या मिलता है?**
> - 17 ready-made strategies — ट्रेंड राइडर, मोमेंटम, MACD, RSI, सब कुछ
> - Visual Strategy Builder — कोडिंग नहीं आती? कोई बात नहीं, blocks drag करके strategy बनाओ
> - AI Assistant — हिंदी में पूछो 'मेरी पोजीशन क्या है?' — AI बताएगा
> - 10 brokers का सपोर्ट — Fyers, Angel One, Zerodha, Dhan, Upstox, सब
> - Backtesting — लाखों रुपए लगाने से पहले पिछले डेटा पर test करो
> - Risk Management — किल स्विच, डेली लॉस लिमिट, सब कुछ

> **कितने का है?**
> - Free से शुरू करो (Paper trading with ₹1Cr virtual capital)
> - Monthly ₹15,500 — Pro features के साथ
> - सबसे पॉपुलर: Half-Yearly ₹69,500 (बचत के साथ)

> **कौन use कर सकता है?**
> - नया ट्रेडर हो? Paper trading से सीखो
> - एक्सपीरिएंस्ड हो? Strategies deploy करो, time बचाओ
> - बिजी प्रोफेशनल हो? AI को ट्रेड करने दो

> एक बार demo दिखाऊं?"

### Common Objections — जवाब

| Objection | Answer |
|-----------|--------|
| "बहुत महंगा है" | "सर, ₹15,500 में आपको पूरा ट्रेडिंग डेस्क मिल रहा है — AI, strategies, risk management, all brokers. एक अच्छा indicator subscription साल का ₹50,000+ होता है. यहाँ सब included है." |
| "मुझे कोडिंग नहीं आती" | "कोडिंग की ज़रूरत नहीं है। Visual Builder है — जैसे canva में डिज़ाइन बनाते हैं, वैसे ही blocks drag करके strategy बनाइए।" |
| "मेरा broker support नहीं करता" | "हम 10 brokers support करते हैं — Fyers, Angel, Zerodha, Dhan, Upstox, Alice Blue, 5Paisa, Finvasia, Flattrade, Kotak. आपका broker तो इन्हीं में से एक होगा।" |
| "पैसे डूब जाएंगे" | "हर strategy पहले backtest कर सकते हैं — पिछले 5 साल के डेटा पर test करो, फिर deploy करो। Paper trading से शुरू करो, जब confidence हो तब LIVE जाओ। Risk management भी है — daily loss limit, kill switch।" |
| "AI पर भरोसा नहीं" | "AI सिर्फ assistant है — वो आपकी जानकारी देता है, analysis करता है। फैसला आपका होता है। हाँ, strategies auto-trade कर सकती हैं, लेकिन वो आपके set किए हुए rules के according।" |
| "मार्केट बंद है अभी" | "कोई बात नहीं। Backtest कर सकते हैं, strategies build कर सकते हैं, AI से बात कर सकते हैं। Paper trading भी चलता है। Admin trades market closed में भी काम करती हैं।" |

---

## Part 4: Sales Pitch — शुद्ध हिंदी में

### 3-मिनट की सेल्स पिच

> "नमस्ते सर! क्या आप शेयर बाजार में ट्रेडिंग करते हैं? आजकल ट्रेडिंग में ऑटोमेशन का ज़माना है — और यही हम लेकर आए हैं।

> **TradeMetrix Terminal** एक अल्गोरिदमिक ट्रेडिंग प्लेटफॉर्म है। यानी एक ऐसा सॉफ्टवेयर जो आपकी तरफ से ऑटोमैटिक ट्रेड कर सकता है — बिना आपके screen के सामने बैठे, बिना emotion के, बिना गलती के।

> **हमारे पास क्या है?**

> **पहला — 17 तैयार स्ट्रेटेजीज़**
> ट्रेंड राइडर, मोमेंटम ब्रेकआउट, MACD क्रॉस, VWAP बैंड, RSI मीन रिवर्जन, बोलिंजर बैंडिट, ORB प्रो, SMC स्नाइपर, लॉन्ग स्ट्रैडल, ऑप्शन व्हील — हर तरह की ट्रेडिंग के लिए कुछ न कुछ।

> **दूसरा — विज़ुअल स्ट्रेटेजी बिल्डर**
> अगर तैयार स्ट्रेटेजी काम नहीं आती, तो अपनी खुद की बनाइए। कोडिंग की ज़रूरत नहीं — blocks को drag करके जोड़िए, indicators select कीजिए, entry/exit conditions set कीजिए, एक क्लिक में deploy कीजिए।

> **तीसरा — AI असिस्टेंट**
> 'मेरी पोजीशन क्या है?' — AI बताएगा। 'आज का P&L क्या है?' — AI calculate करेगा। 'मेरी ट्रेडिंग कैसी है?' — AI analysis देगा। हिंदी में पूछिए, हिंदी में जवाब।

> **चौथा — 10 ब्रोकर्स का सपोर्ट**
> फ़ायर्स, एंजल वन, ज़ेरोधा, धन, अपस्टॉक्स, एलिस ब्लू, 5पैसा, फिनवासिया, फ्लैटट्रेड, कोटक — आपका जो भी ब्रोकर हो, हमसे कनेक्ट हो सकता है।

> **पाँचवाँ — रिस्क मैनेजमेंट**
> किल स्विच — एक क्लिक में सारी ट्रेडिंग बंद। डेली लॉस लिमिट — जितना लॉस होना चाहिए उतना ही होगा। मैक्स पोजीशन साइज़ — एक साथ ज़्यादा risk नहीं ले सकते।

> **कीमत क्या है?**
> - मुफ़्त: Paper trading से शुरू करें (₹1 करोड़ का वर्चुअल कैपिटल)
> - मंथली: ₹15,500
> - क्वार्टरली: ₹35,500
> - हाफ-ईयरली: ₹69,500 — सबसे ज़्यादा लोकप्रिय
> - ईयरली: ₹1,25,000

> **कौन खरीद सकता है?**
> - नए ट्रेडर — paper trading से सीखें
> - एक्सपीरिएंस्ड ट्रेडर — auto-trading से time बचाएँ
> - बिजी प्रोफेशनल — AI को ट्रेड करने दें
> - ट्रेडिंग ग्रुप्स — एक साथ मैनेज करें

> क्या मैं एक डेमो दिखा सकता हूँ?"

### कॉमन आपत्तियाँ — जवाब

| आपत्ति | जवाब |
|--------|-------|
| "यह तो बहुत महँगा है" | "सर, सोचिए — एक अच्छे इंडिकेटर का सब्सक्रिप्शन ₹50,000+ सालाना होता है। यहाँ AI, स्ट्रेटेजीज़, रिस्क मैनेजमेंट, बैकटेस्टिंग, 10 ब्रोकर्स — सब कुछ एक साथ मिल रहा है। ₹15,500 प्रति माह एक ट्रेडिंग डेस्क के हिसाब से बहुत कम है।" |
| "कोडिंग नहीं आती" | "कोडिंग की ज़रूरत ही नहीं है। विज़ुअल बिल्डर है — जैसे कैनवा या फ़ोटोशॉप में आप डिज़ाइन बनाते हैं, वैसे ही आप blocks को drag करके स्ट्रेटेजी बना सकते हैं। इसके अलावा 17 ready-made strategies भी हैं — बस assign कीजिए और चलने दीजिए।" |
| "मेरा ब्रोकर सपोर्ट नहीं करता" | "हम 10 ब्रोकर्स को सपोर्ट करते हैं। उसमें से एक आपका ब्रोकर ज़रूर होगा — Fyers, Angel One, Zerodha, Dhan, Upstox, Alice Blue, 5Paisa, Finvasia, Flattrade, Kotak। अगर फिर भी नहीं है, तो कोई बात नहीं — paper trading से शुरू करें।" |
| "पैसे डूबने का डर है" | "बिल्कुल सही सवाल है। इसीलिए हमारे पास है: (1) बैकटेस्टिंग — पिछले डेटा पर strategy test करें, (2) Paper trading — ₹1 करोड़ virtual capital के साथ practice करें, (3) Risk management — किल स्विच, डेली लॉस लिमिट, मैक्स पोजीशन साइज़। आपका पैसा सुरक्षित है।" |
| "मार्केट बंद है, अब क्या फ़ायदा" | "मार्केट बंद होने पर भी बहुत कुछ कर सकते हैं — नई strategies बना सकते हैं, पुरानी का backtest कर सकते हैं, AI से analysis करवा सकते हैं, trade journal देख सकते हैं। और हाँ — अगर आप एडमिन हैं, तो मार्केट बंद होने पर भी trade place कर सकते हैं।" |

### Closing Lines (समापन के लिए)

> "सर, आज ही ट्रायल लीजिए — **www.trademetrix.tech** पर जाइए, फ्री में रजिस्टर कीजिए, ₹1 करोड़ का वर्चुअल कैपिटल पाइए और paper trading शुरू कीजिए। कोई रिस्क नहीं, कोई investment नहीं। अगर पसंद आया तो subscription लीजिएगा। क्या मैं आपको sign up करने में help कर सकता हूँ?"

### Targeted Pitches (लक्ष्य के अनुसार)

#### नए ट्रेडर के लिए
> "बिना experience के लाखों का नुकसान हो सकता है। पहले paper trading से सीखिए — ₹1 करोड़ का virtual capital, real जैसा experience। जब confidence हो तब LIVE जाइए।"

#### एक्सपीरिएंस्ड ट्रेडर के लिए
> "आपकी strategy है, लेकिन उसे manually execute करने में time और emotion waste होता है। हमारे प्लेटफॉर्म पर strategy deploy करें, वह अपने आप चलेगी — जब आप सो रहे हों तब भी।"

#### बिजी प्रोफेशनल के लिए
> "नौकरी करते हैं और ट्रेडिंग भी करनी है? Screen के सामने नहीं बैठ सकते? AI को command दीजिए — 'buy NIFTY 24000 CE' — और वह trade place कर देगा। या फिर auto-trading strategy लगा दीजिए, वह खुद manage करेगी।"

#### ट्रेडिंग ग्रुप/फर्म के लिए
> "एक साथ कई users को manage करना है? Admin panel से सबको strategies assign करें, trades broadcast करें, risk monitor करें। 10 brokers, unlimited users, एक डैशबोर्ड।"

---

## Part 5: Quick Reference — Key Selling Points

### Top 5 Reasons to Buy
1. **All-in-One Platform** — Strategies, AI, Risk, Brokers, Backtesting — सब एक जगह
2. **No Coding Required** — Visual Builder + 17 Ready-Made Strategies
3. **AI-Powered** — Natural language commands, trade analysis, copilot
4. **10 Brokers** — जोड़िए अपने broker को, या Paper Trading से शुरू कीजिए
5. **Risk First** — Fail-close design, kill switch, daily limits — आपका पैसा सुरक्षित

### Price Summary
| Plan | Price | Best For |
|------|-------|----------|
| **Free** | ₹0 | Paper trading, learning |
| **Monthly** | ₹15,500 | Trial, short-term |
| **Quarterly** | ₹35,500 (₹11,833/mo) | Medium-term |
| **Half-Yearly** | ₹69,500 (₹11,583/mo) ⭐ | Best value |
| **Yearly** | ₹1,25,000 (₹10,416/mo) | Serious traders |

### Supported for Demo
अगर client को demo दिखाना है:
1. **www.trademetrix.tech** पर जाएँ
2. OTP से login करें (कोई password नहीं चाहिए)
3. **Dashboard** दिखाएँ — portfolio summary, positions
4. **Strategies → Catalog** — 17 ready-made strategies दिखाएँ
5. **Terminal → Builder** — Visual builder drag-drop दिखाएँ
6. **AI Desk** — "Show my positions" कमांड दिखाएँ
7. **Admin Panel** (अगर accessible हो) — user management दिखाएँ

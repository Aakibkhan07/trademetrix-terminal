from datetime import date, timedelta


LOT_SIZES: dict[str, int] = {
    "NIFTY": 65,
    "SENSEX": 20,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
}

STRIKE_INTERVALS: dict[str, int] = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
    "FINNIFTY": 50,
    "SENSEX": 100,
}

# NIFTY weekly expiry changed from Thu(3)→Tue(1) post-Sept 2025 circular.
# These are fallbacks only — runtime resolve from option chain is authoritative.
WEEKLY_EXPIRY_MAP: dict[str, int] = {
    "NIFTY": 1,
    "BANKNIFTY": 3,
    "FINNIFTY": 2,
    "SENSEX": 3,
    "MIDCPNIFTY": 3,
}

MONTH_CODES = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


def get_weekly_expiry(symbol: str, ref_date: date | None = None) -> date:
    if ref_date is None:
        from datetime import datetime
        ref_date = datetime.now().date()
    expiry_weekday = WEEKLY_EXPIRY_MAP.get(symbol.upper(), 3)
    days_ahead = expiry_weekday - ref_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return ref_date + timedelta(days=days_ahead)


def get_monthly_expiry(symbol: str, ref_date: date | None = None) -> date:
    if ref_date is None:
        from datetime import datetime
        ref_date = datetime.now().date()
    import calendar
    last_day = calendar.monthrange(ref_date.year, ref_date.month)[1]
    last_date = date(ref_date.year, ref_date.month, last_day)
    while last_date.weekday() != 3:
        last_date -= timedelta(days=1)
    return last_date


def format_fyers_option_symbol(symbol: str, strike: float, option_type: str, expiry_date: date | None = None) -> str:
    if expiry_date is None:
        expiry_date = get_weekly_expiry(symbol)
    dd = f"{expiry_date.day:02d}"
    yy = str(expiry_date.year)[-2:]
    month_code = MONTH_CODES[expiry_date.month]
    strike_int = int(strike)
    return f"NSE:{symbol.upper()}{dd}{month_code}{yy}{strike_int}{option_type.upper()}"


def format_fyers_future_symbol(symbol: str, expiry_date: date | None = None) -> str:
    if expiry_date is None:
        expiry_date = get_weekly_expiry(symbol)
    yy = str(expiry_date.year)[-2:]
    month_code = MONTH_CODES[expiry_date.month]
    return f"NSE:{symbol.upper()}{yy}{month_code}"

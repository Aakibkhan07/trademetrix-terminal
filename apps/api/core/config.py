import ast
from urllib.parse import urlsplit
import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    app_name: str = "Trade Metrix API"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str

    secret_key: str
    encryption_key: str
    encryption_keys: str = ""
    cors_origins: str = "http://localhost:3000"
    cookie_domain: str = ""

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_plan_monthly: str = ""
    razorpay_plan_quarterly: str = ""
    razorpay_plan_halfyearly: str = ""
    razorpay_plan_yearly: str = ""
    paytm_merchant_id: str = ""
    paytm_merchant_key: str = ""

    openrouter_api_key: str = ""

    redis_url: str = "redis://localhost:6379/0"
    supabase_db_url: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@trademetrix.tech"

    resend_api_key: str = ""

    fast2sms_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    twilio_sms_from: str = ""

    sentry_dsn: str = ""
    sentry_env: str = "development"

    dotenv_key: str = ""
    env: str = "development"
    tradingview_webhook_secret: str = ""
    frontend_url: str = "https://ai.trademetrix.tech"
    fyers_redirect_uri: str = ""
    dhan_redirect_uri: str = ""
    upstox_redirect_uri: str = ""
    zerodha_redirect_uri: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_bot_username: str = ""  # e.g. "TradeMetrixAlertsBot" — for deep links; auto-fetched via getMe when empty

    request_timeout_seconds: int = 60
    max_request_size_bytes: int = 102400
    broker_request_timeout: int = 8
    broker_connect_timeout: int = 5

    ws_reconnect_max_retries: int = 10
    ws_reconnect_base_delay: float = 1.0
    ws_reconnect_max_delay: float = 30.0
    ws_heartbeat_interval: int = 30
    ws_ping_interval: int = 30
    user_strategy_max_lots: int = 10
    default_buyer_user_id: str = "fa668109-4b1e-4758-a49b-015027ea4115"  # override via DEFAULT_BUYER_USER_ID env

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins
        parsed: list[str] | None = None
        try:
            value = ast.literal_eval(raw)
            if isinstance(value, list):
                parsed = [str(o).strip() for o in value]
        except (ValueError, SyntaxError):
            pass
        if parsed is None:
            parsed = [origin.strip() for origin in raw.split(",") if origin.strip()]
        return self._with_loopback_aliases(parsed)

    def _with_loopback_aliases(self, origins: list[str]) -> list[str]:
        """Add the other spelling of each loopback origin, outside production only.

        `localhost` and `127.0.0.1` are the same machine but different cookie scopes. This bites in
        a way that is genuinely hard to see, because each half of the app works on the host the
        config names and fails on the other:

          * the API sets `csrf_token` on the host it is served from, so a page on the *other*
            loopback spelling cannot read it — `document.cookie` is empty, `X-CSRF-Token` is never
            attached, and every POST/PUT/DELETE answers 403
          * `CORS_ORIGINS=http://localhost:3000` rejects the preflight from `127.0.0.1:3000` with
            a bodiless 400, which the browser reports as `net::ERR_FAILED` — the request is not
            even attempted

        So a local stack configured with one spelling cannot write anything, and reads still work,
        so it looks healthy. Serving the web app at `localhost` and pointing it at a `127.0.0.1`
        API fails the first way; the reverse fails the second. There is no single spelling that
        satisfies both halves unless both are allowed.

        Loopback origins are not a security boundary — they are this machine — so widening them
        outside production costs nothing. **Production is untouched**: with `ENV=production` the list
        is returned exactly as configured, because there the origins are real hosts and silently
        adding aliases to an allow-list would be a security change, not a convenience.
        """
        if self.env == "production":
            return origins
        aliases = {"localhost": "127.0.0.1", "127.0.0.1": "localhost"}
        extra: list[str] = []
        for origin in origins:
            try:
                parsed = urlsplit(origin)
            except ValueError:
                continue
            host = (parsed.hostname or "").lower()
            swap = aliases.get(host)
            if not swap:
                continue
            candidate = origin.replace(parsed.hostname or "", swap, 1)
            if candidate not in origins and candidate not in extra:
                extra.append(candidate)
        return origins + extra

    @model_validator(mode="after")
    def _validate_secrets(self):
        missing = []
        if not self.supabase_url:
            missing.append("supabase_url")
        if not self.supabase_service_key:
            missing.append("supabase_service_key")
        if not self.supabase_anon_key:
            missing.append("supabase_anon_key")
        if not self.secret_key:
            missing.append("secret_key")
        if self.secret_key == "dev-secret-key-not-for-production":
            logger.warning("SECRET_KEY is set to the default dev value — replace with a secure random key in production")
        if not self.encryption_key:
            missing.append("encryption_key")
        if missing:
            logger.warning("Critical secrets not configured: %s", ", ".join(missing))
        if not self.tradingview_webhook_secret:
            logger.warning("TRADINGVIEW_WEBHOOK_SECRET not set — webhook signatures will not be verified")
        if not self.openrouter_api_key:
            logger.info("OPENROUTER_API_KEY not set — AI features will be unavailable")
        if not self.redis_url or self.redis_url == "redis://localhost:6379/0":
            logger.info("REDIS_URL using default — caching will use local Redis")
        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

STREAMING_SUPPORTED = {"fyers", "angelone", "dhan", "upstox"}

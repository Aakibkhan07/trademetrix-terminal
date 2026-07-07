import ast
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

    gemini_api_key: str = ""

    redis_url: str = "redis://localhost:6379/0"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@trademetrix.tech"

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

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    request_timeout_seconds: int = 60
    max_request_size_bytes: int = 102400
    broker_request_timeout: int = 8

    broker_connect_timeout: int = 5
    user_strategy_max_lots: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            pass
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

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
        if not self.encryption_key:
            missing.append("encryption_key")
        if missing:
            logger.warning("Critical secrets not configured: %s", ", ".join(missing))
        if not self.tradingview_webhook_secret:
            logger.warning("TRADINGVIEW_WEBHOOK_SECRET not set — webhook signatures will not be verified")
        if not self.gemini_api_key:
            logger.info("GEMINI_API_KEY not set — AI features will be unavailable")
        if not self.redis_url or self.redis_url == "redis://localhost:6379/0":
            logger.info("REDIS_URL using default — caching will use local Redis")
        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

STREAMING_SUPPORTED = {"fyers", "angelone"}

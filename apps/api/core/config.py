import ast

from pydantic_settings import BaseSettings


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

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    paytm_merchant_id: str = ""
    paytm_merchant_key: str = ""

    gemini_api_key: str = ""

    redis_url: str = "redis://localhost:6379/0"

    sentry_dsn: str = ""
    sentry_env: str = "development"

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

import logging

from core.config import settings

logger = logging.getLogger(__name__)


def init_sentry():
    dsn = getattr(settings, "sentry_dsn", "")
    env = getattr(settings, "sentry_env", "development")

    if not dsn:
        logger.info("Sentry DSN not configured, skipping")
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
        ],
        send_default_pii=False,
    )
    logger.info("Sentry initialized for environment=%s", env)

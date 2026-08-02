"""Unified Broker SDK — typed error taxonomy + error translator tests."""

import pytest

from brokers.sdk.errors import (
    BrokerAuthError,
    BrokerConnectionError,
    BrokerError,
    BrokerRateLimitError,
    BrokerServerError,
    BrokerTimeoutError,
    BrokerValidationError,
    BrokerWAFError,
    MarginInsufficientError,
    OrderRejectedError,
    UnsupportedFeatureError,
    parse_retry_after,
    translate_broker_error,
    translate_exception,
)


class TestErrorTaxonomy:
    def test_hierarchy(self):
        assert issubclass(BrokerRateLimitError, BrokerError)
        assert issubclass(BrokerWAFError, BrokerError)
        assert issubclass(OrderRejectedError, BrokerError)
        assert issubclass(MarginInsufficientError, OrderRejectedError)

    def test_retryable_flags(self):
        assert BrokerRateLimitError().retryable is True
        assert BrokerAuthError().retryable is True
        assert BrokerConnectionError().retryable is True
        assert BrokerTimeoutError().retryable is True
        assert BrokerServerError().retryable is True
        assert BrokerWAFError().retryable is False
        assert BrokerValidationError().retryable is False
        assert OrderRejectedError().retryable is False
        assert UnsupportedFeatureError("x").retryable is False

    def test_unsupported_feature_contract(self):
        err = UnsupportedFeatureError("websocket", broker="fivepaisa")
        assert err.code == "unsupported_feature"
        assert err.broker == "fivepaisa"
        assert err.feature == "websocket"
        assert "websocket" in err.message
        info = err.info()
        assert info.code == "unsupported_feature"
        assert info.retryable is False

    def test_info_payload(self):
        err = BrokerRateLimitError(retry_after=12.0, broker="fyers", detail="slow down")
        info = err.info()
        assert info.http_status == 429
        assert info.retry_after == 12.0
        assert info.broker == "fyers"

    def test_message_defaults_to_code(self):
        assert BrokerWAFError().message == "Broker endpoint blocked by Cloudflare WAF"


class TestErrorTranslator:
    def test_429_maps_to_rate_limit(self):
        err = translate_broker_error(status_code=429, broker="fyers")
        assert isinstance(err, BrokerRateLimitError)
        assert err.retry_after is None

    def test_1015_maps_to_rate_limit(self):
        err = translate_broker_error(status_code=1015)
        assert isinstance(err, BrokerRateLimitError)

    def test_retry_after_header_honoured(self):
        err = translate_broker_error(status_code=429, headers={"Retry-After": "30"})
        assert isinstance(err, BrokerRateLimitError)
        assert err.retry_after == 30.0

    def test_403_maps_to_waf(self):
        err = translate_broker_error(status_code=403)
        assert isinstance(err, BrokerWAFError)
        assert err.retryable is False

    def test_401_maps_to_auth(self):
        err = translate_broker_error(status_code=401)
        assert isinstance(err, BrokerAuthError)

    def test_token_keywords_map_to_auth_even_on_200ish_body(self):
        err = translate_broker_error(status_code=400, message="Invalid access token")
        assert isinstance(err, BrokerAuthError)

    def test_500_maps_to_server_error(self):
        err = translate_broker_error(status_code=500)
        assert isinstance(err, BrokerServerError)
        assert err.retryable is True

    def test_plain_4xx_maps_to_validation(self):
        err = translate_broker_error(status_code=400, message="invalid symbol")
        assert isinstance(err, BrokerValidationError)
        assert err.retryable is False

    def test_unsupported_status_maps_to_base(self):
        err = translate_broker_error(status_code=299)
        assert isinstance(err, BrokerError)

    def test_translate_exception_timeout(self):
        import asyncio

        err = translate_exception(asyncio.TimeoutError())
        assert isinstance(err, BrokerTimeoutError)

    def test_translate_exception_connection(self):
        err = translate_exception(ConnectionResetError("reset"))
        assert isinstance(err, BrokerConnectionError)

    def test_translate_exception_passthrough_broker_error(self):
        original = BrokerWAFError(broker="fyers")
        translated = translate_exception(original)
        assert translated is original

    def test_parse_retry_after(self):
        assert parse_retry_after("15") == 15.0
        assert parse_retry_after(5) == 5.0
        assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") is None
        assert parse_retry_after(None) is None


class TestMarginError:
    def test_margin_insufficient_subclass(self):
        err = MarginInsufficientError("not enough margin")
        assert err.code == "insufficient_margin"
        assert isinstance(err, OrderRejectedError)

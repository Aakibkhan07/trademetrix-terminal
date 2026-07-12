from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.broker_service import BrokerService
from domain.broker import BrokerCredential, BrokerTokenResult


@pytest.fixture
def repo() -> MagicMock:
    m = MagicMock()
    m.get_by_user_and_broker = AsyncMock()
    m.get_by_user_and_broker_full = AsyncMock()
    m.upsert_credentials = AsyncMock()
    m.delete_credentials = AsyncMock()
    m.list_credentials = AsyncMock()
    m.activate_broker = AsyncMock()
    m.update_access_token = AsyncMock()
    m.clear_access_token = AsyncMock()
    return m


@pytest.fixture
def svc(repo) -> BrokerService:
    return BrokerService(repo)


@pytest.fixture
def sample_cred() -> BrokerCredential:
    return BrokerCredential(
        id="cred-1",
        user_id="user-1",
        broker="fyers",
        encrypted_api_key="gAAAAABtest_encrypted_key==",
        encrypted_secret_key="gAAAAABtest_encrypted_secret==",
        is_active=True,
    )


class TestSaveCredentials:
    @pytest.mark.asyncio
    async def test_saves_unsupported_broker_raises(self, svc, repo) -> None:
        with patch.object(svc, "_broker_supported", return_value=False):
            with pytest.raises(ValueError, match="Unsupported broker"):
                await svc.save_credentials("u1", "unknown", "key", "secret")

    @pytest.mark.asyncio
    async def test_saves_supported_broker(self, svc, repo, sample_cred) -> None:
        repo.upsert_credentials.return_value = sample_cred
        with patch.object(svc, "_broker_supported", return_value=True):
            result = await svc.save_credentials("u1", "fyers", "key", "secret")
        repo.upsert_credentials.assert_awaited_once_with("u1", "fyers", "key", "secret", None, None)
        assert result.id == "cred-1"

    @pytest.mark.asyncio
    async def test_saves_with_access_token(self, svc, repo, sample_cred) -> None:
        repo.upsert_credentials.return_value = sample_cred
        with patch.object(svc, "_broker_supported", return_value=True):
            result = await svc.save_credentials("u1", "fyers", "key", "secret", access_token="tok")
        repo.upsert_credentials.assert_awaited_once_with("u1", "fyers", "key", "secret", "tok", None)
        assert result.id == "cred-1"

    @pytest.mark.asyncio
    async def test_saves_with_additional_params(self, svc, repo, sample_cred) -> None:
        repo.upsert_credentials.return_value = sample_cred
        extra = {"totp_secret": "sekret"}
        with patch.object(svc, "_broker_supported", return_value=True):
            result = await svc.save_credentials("u1", "fyers", "key", "secret", additional_params=extra)
        repo.upsert_credentials.assert_awaited_once_with("u1", "fyers", "key", "secret", None, extra)
        assert result.id == "cred-1"


class TestListCredentials:
    @pytest.mark.asyncio
    async def test_returns_repo_result(self, svc, repo) -> None:
        expected = [{"id": "c1", "broker": "fyers"}]
        repo.list_credentials.return_value = expected
        result = await svc.list_credentials("u1")
        repo.list_credentials.assert_awaited_once_with("u1")
        assert result == expected

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, svc, repo) -> None:
        repo.list_credentials.return_value = []
        result = await svc.list_credentials("u1")
        assert result == []


class TestDeleteCredentials:
    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(self, svc, repo) -> None:
        repo.delete_credentials.return_value = True
        result = await svc.delete_credentials("u1", "fyers")
        repo.delete_credentials.assert_awaited_once_with("u1", "fyers")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, svc, repo) -> None:
        repo.delete_credentials.return_value = False
        result = await svc.delete_credentials("u1", "fyers")
        assert result is False


class TestActivateBroker:
    @pytest.mark.asyncio
    async def test_activates_and_returns_true(self, svc, repo) -> None:
        repo.activate_broker.return_value = True
        result = await svc.activate_broker("u1", "fyers")
        repo.activate_broker.assert_awaited_once_with("u1", "fyers")
        assert result is True


class TestGetAuthUrl:
    @patch("core.security.decrypt_broker_credentials")
    @patch("application.services.broker_service.get_oauth_provider")
    @patch("application.services.broker_service.get_redirect_uri")
    @pytest.mark.asyncio
    async def test_returns_auth_url(self, mock_redirect, mock_provider, mock_decrypt, svc, repo, sample_cred) -> None:
        repo.get_by_user_and_broker.return_value = sample_cred
        repo.get_by_user_and_broker_full.return_value = sample_cred
        mock_decrypt.return_value = "client-123"
        mock_redirect.return_value = "https://example.com/callback"
        mock_provider.return_value.build_auth_url.return_value = "https://oauth.example.com/auth?client_id=client-123"

        url = await svc.get_auth_url("u1", "fyers")

        assert url == "https://oauth.example.com/auth?client_id=client-123"
        mock_decrypt.assert_called_once_with(sample_cred.encrypted_api_key)
        mock_provider.return_value.build_auth_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_when_no_cred(self, svc, repo) -> None:
        repo.get_by_user_and_broker.return_value = None
        with pytest.raises(ValueError, match="Save Fyers credentials first"):
            await svc.get_auth_url("u1", "fyers")

    @pytest.mark.asyncio
    async def test_raises_when_client_id_empty(self, svc, repo, sample_cred) -> None:
        repo.get_by_user_and_broker.return_value = sample_cred
        repo.get_by_user_and_broker_full.return_value = sample_cred
        with patch.object(svc, "_decrypt", return_value=""):
            with pytest.raises(ValueError, match="Decrypted client ID not found"):
                await svc.get_auth_url("u1", "fyers")


class TestReAuth:
    @pytest.mark.asyncio
    async def test_raises_when_no_cred(self, svc, repo) -> None:
        repo.get_by_user_and_broker.return_value = None
        with pytest.raises(ValueError, match="No Fyers credentials found"):
            await svc.re_auth("u1", "fyers")

    @pytest.mark.asyncio
    async def test_clears_token_and_returns_auth_url(self, svc, repo, sample_cred) -> None:
        repo.get_by_user_and_broker.return_value = sample_cred
        with patch.object(svc, "get_auth_url", AsyncMock(return_value="https://auth.url")):
            url = await svc.re_auth("u1", "fyers")
        repo.clear_access_token.assert_awaited_once_with("cred-1")
        assert url == "https://auth.url"


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_raises_when_no_cred(self, svc, repo) -> None:
        repo.get_by_user_and_broker_full.return_value = None
        with pytest.raises(ValueError, match="No Fyers credentials found"):
            await svc.exchange_code("u1", "fyers", "code123")

    @patch("core.security.decrypt_broker_credentials")
    @patch("application.services.broker_service.get_oauth_provider")
    @patch("application.services.broker_service.get_redirect_uri")
    @pytest.mark.asyncio
    async def test_exchanges_code_and_updates_token(self, mock_redirect, mock_provider, mock_decrypt, svc, repo, sample_cred) -> None:
        repo.get_by_user_and_broker_full.return_value = sample_cred
        mock_decrypt.side_effect = lambda x: {"enc1": "client-1", "enc2": "secret-1"}.get(x, x)
        mock_redirect.return_value = "https://example.com/callback"
        mock_provider.return_value.exchange_code = AsyncMock(return_value=BrokerTokenResult(access_token="new-token", refresh_token="refresh-1"))

        msg = await svc.exchange_code("u1", "fyers", "code123")

        assert msg == "Fyers authenticated successfully!"
        repo.update_access_token.assert_awaited_once_with("cred-1", "new-token", "refresh-1")


class TestHandleCallback:
    @pytest.mark.asyncio
    async def test_missing_state_returns_false(self, svc) -> None:
        ok, msg = await svc.handle_callback("fyers", "code123", None)
        assert ok is False
        assert msg == "Missing state parameter"

    @pytest.mark.asyncio
    async def test_no_cred_returns_false(self, svc, repo) -> None:
        repo.get_by_user_and_broker_full.return_value = None
        ok, msg = await svc.handle_callback("fyers", "code123", "user-1")
        assert ok is False
        assert "No Fyers credentials found" in msg

    @pytest.mark.asyncio
    async def test_success_flow_returns_true(self, svc, repo, sample_cred) -> None:
        repo.get_by_user_and_broker_full.return_value = sample_cred
        with (
            patch.object(svc, "_decrypt", return_value="decrypted"),
            patch("application.services.broker_service.get_oauth_provider") as mock_provider,
            patch("application.services.broker_service.get_redirect_uri", return_value="https://cb"),
        ):
            mock_provider.return_value.exchange_code = AsyncMock(return_value=BrokerTokenResult(access_token="tok"))
            ok, msg = await svc.handle_callback("fyers", "code123", "user-1")
        assert ok is True
        assert msg == "success"
        repo.update_access_token.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, svc, repo, sample_cred) -> None:
        repo.get_by_user_and_broker_full.return_value = sample_cred
        with (
            patch.object(svc, "_decrypt", side_effect=ValueError("boom")),
            patch("application.services.broker_service.get_redirect_uri"),
        ):
            ok, msg = await svc.handle_callback("fyers", "code123", "user-1")
        assert ok is False
        assert "boom" in msg

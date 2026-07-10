import logging

from application.interfaces.broker_oauth import BrokerOAuthProvider, BrokerRepository
from domain.broker import BrokerOAuthConfig, BrokerCredential
from infrastructure.oauth_providers import get_oauth_provider, get_redirect_uri

logger = logging.getLogger(__name__)


class BrokerService:
    def __init__(self, repo: BrokerRepository):
        self._repo = repo

    async def list_credentials(self, user_id: str) -> list[dict]:
        return await self._repo.list_credentials(user_id)

    async def save_credentials(self, user_id: str, broker: str, api_key: str, secret_key: str, access_token: str | None = None, additional_params: dict | None = None) -> BrokerCredential:
        if not self._broker_supported(broker):
            raise ValueError(f"Unsupported broker: {broker}")
        return await self._repo.upsert_credentials(user_id, broker, api_key, secret_key, access_token, additional_params)

    async def delete_credentials(self, user_id: str, broker: str) -> bool:
        return await self._repo.delete_credentials(user_id, broker)

    async def activate_broker(self, user_id: str, broker: str) -> bool:
        return await self._repo.activate_broker(user_id, broker)

    async def get_auth_url(self, user_id: str, broker: str) -> str:
        cred = await self._repo.get_by_user_and_broker(user_id, broker)
        if not cred:
            raise ValueError(f"Save {broker.title()} credentials first")
        cred_full = await self._repo.get_by_user_and_broker_full(user_id, broker)
        client_id = self._decrypt(cred_full.encrypted_api_key) if cred_full else ""
        if not client_id:
            raise ValueError(f"Decrypted client ID not found for {broker}")

        provider = get_oauth_provider(broker)
        config = BrokerOAuthConfig(client_id=client_id, redirect_uri=get_redirect_uri(broker))
        return provider.build_auth_url(config, user_id)

    async def re_auth(self, user_id: str, broker: str) -> str:
        cred = await self._repo.get_by_user_and_broker(user_id, broker)
        if not cred:
            raise ValueError(f"No {broker.title()} credentials found")
        await self._repo.clear_access_token(cred.id)
        return await self.get_auth_url(user_id, broker)

    async def exchange_code(self, user_id: str, broker: str, code: str) -> str:
        cred = await self._repo.get_by_user_and_broker_full(user_id, broker)
        if not cred:
            raise ValueError(f"No {broker.title()} credentials found")

        client_id = self._decrypt(cred.encrypted_api_key)
        secret_key = self._decrypt(cred.encrypted_secret_key)

        provider = get_oauth_provider(broker)
        config = BrokerOAuthConfig(client_id=client_id, redirect_uri=get_redirect_uri(broker))
        result = await provider.exchange_code(config, secret_key, code)

        await self._repo.update_access_token(cred.id, result.access_token, result.refresh_token)
        return f"{broker.title()} authenticated successfully!"

    async def handle_callback(self, broker: str, code: str, state: str | None) -> tuple[bool, str]:
        if not state:
            return False, "Missing state parameter"
        try:
            cred = await self._repo.get_by_user_and_broker_full(state, broker)
            if not cred:
                return False, f"No {broker.title()} credentials found"

            client_id = self._decrypt(cred.encrypted_api_key)
            secret_key = self._decrypt(cred.encrypted_secret_key)

            provider = get_oauth_provider(broker)
            config = BrokerOAuthConfig(client_id=client_id, redirect_uri=get_redirect_uri(broker))
            result = await provider.exchange_code(config, secret_key, code)
            await self._repo.update_access_token(cred.id, result.access_token, result.refresh_token)
            return True, "success"
        except Exception as e:
            logger.error("%s callback failed: %s", broker, e)
            return False, str(e)

    def _decrypt(self, encrypted: str | None) -> str:
        from core.security import decrypt_broker_credentials
        if not encrypted:
            return ""
        return decrypt_broker_credentials(encrypted)

    def _broker_supported(self, broker: str) -> bool:
        from brokers import list_brokers
        return broker in list_brokers()

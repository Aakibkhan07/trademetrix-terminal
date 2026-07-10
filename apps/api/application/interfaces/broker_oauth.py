from abc import ABC, abstractmethod

from domain.broker import BrokerCredential, BrokerOAuthConfig, BrokerTokenResult


class BrokerOAuthProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def build_auth_url(self, config: BrokerOAuthConfig, state: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, config: BrokerOAuthConfig, secret_key: str, code: str) -> BrokerTokenResult: ...


class BrokerRepository(ABC):
    @abstractmethod
    async def get_by_user_and_broker(self, user_id: str, broker: str) -> BrokerCredential | None: ...

    @abstractmethod
    async def get_by_user_and_broker_full(self, user_id: str, broker: str) -> BrokerCredential | None: ...

    @abstractmethod
    async def upsert_credentials(self, user_id: str, broker: str, api_key: str, secret_key: str, access_token: str | None = None, additional_params: dict | None = None) -> BrokerCredential: ...

    @abstractmethod
    async def delete_credentials(self, user_id: str, broker: str) -> bool: ...

    @abstractmethod
    async def list_credentials(self, user_id: str) -> list[dict]: ...

    @abstractmethod
    async def activate_broker(self, user_id: str, broker: str) -> bool: ...

    @abstractmethod
    async def update_access_token(self, credential_id: str, access_token: str, refresh_token: str | None = None) -> None: ...

    @abstractmethod
    async def clear_access_token(self, credential_id: str) -> None: ...

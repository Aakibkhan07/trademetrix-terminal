from abc import ABC, abstractmethod

from domain.broker import BrokerCredential, BrokerOAuthConfig, BrokerTokenResult

#: The two roles a broker credential can serve. A module-level pair rather than bare
#: string literals in the signatures below: these names are load-bearing in queries that
#: silently pick the wrong row, so a typo should be an import error rather than a query
#: that returns nothing and reads as "not connected".
EXECUTION = "execution"
MARKET_DATA = "market_data"

#: Both values, for validation. A `role` outside this set would match no row, which is
#: indistinguishable from "this tenant has no credential" — so it is refused at the edge.
ROLES = (EXECUTION, MARKET_DATA)


class BrokerOAuthProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def build_auth_url(self, config: BrokerOAuthConfig, state: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, config: BrokerOAuthConfig, secret_key: str, code: str) -> BrokerTokenResult: ...


class BrokerRepository(ABC):
    # Every `role` below defaults to `"execution"`, which is what all of these methods
    # did before the column existed and what every existing caller still means. Making it
    # a defaulted keyword argument rather than a required positional keeps all of them
    # correct without a single call site changing — a signature change that forced 31
    # live tenants' call paths to be edited at once is a signature change that eventually
    # gets one of them wrong.

    @abstractmethod
    async def get_by_user_and_broker(self, user_id: str, broker: str, *, role: str = EXECUTION) -> BrokerCredential | None: ...

    @abstractmethod
    async def get_by_user_and_broker_full(self, user_id: str, broker: str, *, role: str = EXECUTION) -> BrokerCredential | None: ...

    @abstractmethod
    async def upsert_credentials(self, user_id: str, broker: str, api_key: str, secret_key: str, access_token: str | None = None, additional_params: dict | None = None, *, role: str = EXECUTION) -> BrokerCredential: ...

    @abstractmethod
    async def delete_credentials(self, user_id: str, broker: str, *, role: str = EXECUTION) -> bool: ...

    @abstractmethod
    async def list_credentials(self, user_id: str, *, role: str | None = None) -> list[dict]: ...

    @abstractmethod
    async def activate_broker(self, user_id: str, broker: str, *, role: str = EXECUTION) -> bool: ...

    @abstractmethod
    async def update_access_token(self, credential_id: str, access_token: str, refresh_token: str | None = None) -> None: ...

    @abstractmethod
    async def clear_access_token(self, credential_id: str) -> None: ...

    @abstractmethod
    async def get_active_broker(self, user_id: str, *, role: str = EXECUTION) -> str | None: ...

    @abstractmethod
    async def resolve_market_data_broker(self, user_id: str) -> str | None: ...

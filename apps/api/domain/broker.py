from dataclasses import dataclass


@dataclass
class BrokerOAuthConfig:
    client_id: str
    redirect_uri: str


@dataclass
class BrokerTokenResult:
    access_token: str
    refresh_token: str | None = None


@dataclass
class BrokerCredential:
    id: str
    user_id: str
    broker: str
    encrypted_api_key: str
    encrypted_secret_key: str
    encrypted_access_token: str | None = None
    encrypted_refresh_token: str | None = None
    is_active: bool = False
    additional_params: dict | None = None
    #: What this credential is for: `"execution"` places orders, `"market_data"` prices
    #: them. A tenant may hold both, for the same broker name or for two different
    #: brokers.
    #:
    #: Defaults to `"execution"` rather than being required, for two reasons. Every row
    #: that existed before the column did is an execution credential, so the default is
    #: the true value rather than a convenience; and it keeps `BrokerCredential(**row)`
    #: working for callers whose `select` does not name the column, which is every
    #: caller that has not been updated.
    role: str = "execution"

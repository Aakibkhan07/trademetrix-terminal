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

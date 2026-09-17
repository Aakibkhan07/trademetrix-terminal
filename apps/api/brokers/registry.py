BROKER_METADATA: dict[str, dict] = {}

def _register_broker_meta(name: str, meta: dict) -> None:
    BROKER_METADATA[name] = meta

_register_broker_meta("fyers", {
    "display_name": "Fyers",
    "auth_type": "oauth",
    "description": "Connect your Fyers trading account via OAuth",
    "fields": [
        {"key": "client_id", "label": "App ID", "placeholder": "Your Fyers App ID", "required": True},
        {"key": "secret_key", "label": "App Secret", "type": "password", "placeholder": "Your Fyers App Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Go to myapi.fyers.in\n2. Create a new App\n3. Copy App ID & Secret here\n4. Click Authorize to complete OAuth",
    "oauth_available": True,
})

_register_broker_meta("zerodha", {
    "display_name": "Zerodha (Kite)",
    "auth_type": "oauth",
    "description": "Connect your Zerodha Kite account via OAuth",
    "fields": [
        {"key": "client_id", "label": "API Key", "placeholder": "Your Kite API Key", "required": True},
        {"key": "secret_key", "label": "API Secret", "type": "password", "placeholder": "Your Kite API Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Go to console.zerodha.com\n2. Create a Kite API App\n3. Copy API Key & Secret here\n4. Click Authorize to complete OAuth",
    "oauth_available": True,
})

_register_broker_meta("angelone", {
    "display_name": "Angel One",
    "auth_type": "credentials",
    "description": "Login with your Angel One credentials + TOTP",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Your Angel One Client ID", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Trading Password", "required": True},
        {"key": "api_key", "label": "App Key", "placeholder": "Angel App API Key", "required": True},
    ],
    "has_additional_params": True,
    "additional_params_fields": [
        {"key": "totp_secret", "label": "TOTP Secret", "placeholder": "Base32 TOTP secret (optional)", "required": False},
    ],
    "instructions": "1. Enable TOTP in Angel One App\n2. Enter Client Code, Password, and App Key\n3. Enter TOTP Secret if you have one\n4. System will authenticate automatically",
    "oauth_available": False,
})

_register_broker_meta("dhan", {
    "display_name": "Dhan",
    "auth_type": "oauth",
    "description": "Connect your Dhan trading account via OAuth",
    "fields": [
        {"key": "client_id", "label": "Client ID", "placeholder": "Your Dhan Client ID", "required": True},
        {"key": "secret_key", "label": "Client Secret", "type": "password", "placeholder": "Your Dhan Client Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Go to api.dhan.co\n2. Create an application\n3. Copy Client ID & Secret here\n4. Click Authorize to complete OAuth",
    "oauth_available": True,
})

_register_broker_meta("upstox", {
    "display_name": "Upstox",
    "auth_type": "oauth",
    "description": "Connect your Upstox trading account via OAuth",
    "fields": [
        {"key": "client_id", "label": "API Key", "placeholder": "Your Upstox API Key", "required": True},
        {"key": "secret_key", "label": "API Secret", "type": "password", "placeholder": "Your Upstox API Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Go to upstox.com/api\n2. Create an application\n3. Copy API Key & Secret here\n4. Click Authorize to complete OAuth",
    "oauth_available": True,
})

_register_broker_meta("aliceblue", {
    "display_name": "Alice Blue",
    "auth_type": "credentials",
    "description": "Login with Alice Blue credentials + TOTP",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Alice Blue User ID", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Trading Password", "required": True},
    ],
    "has_additional_params": True,
    "additional_params_fields": [
        {"key": "totp_secret", "label": "TOTP Secret", "placeholder": "Base32 TOTP secret (optional)", "required": False},
    ],
    "instructions": "1. Enable TOTP in Alice Blue App\n2. Enter your User ID & Password\n3. Enter TOTP Secret if enabled\n4. System will authenticate automatically",
    "oauth_available": False,
})

_register_broker_meta("fivepaisa", {
    "display_name": "5Paisa",
    "auth_type": "credentials",
    "description": "Login with 5Paisa credentials + PIN + TOTP",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "5Paisa Client Code", "required": True},
        {"key": "api_key", "label": "App Key", "placeholder": "5Paisa App Key", "required": True},
    ],
    "has_additional_params": True,
    "additional_params_fields": [
        {"key": "pin", "label": "PIN", "type": "password", "placeholder": "5Paisa Login PIN", "required": True},
        {"key": "totp_secret", "label": "TOTP Secret", "placeholder": "Base32 TOTP secret (optional)", "required": False},
    ],
    "instructions": "1. Get your App Key from 5Paisa developer portal\n2. Enter Client Code, App Key, PIN\n3. Enter TOTP Secret if enabled\n4. System will authenticate automatically",
    "oauth_available": False,
})

_register_broker_meta("finvasia", {
    "display_name": "Finvasia",
    "auth_type": "credentials",
    "description": "Login with Finvasia credentials + TOTP",
    "fields": [
        {"key": "client_code", "label": "User ID", "placeholder": "Finvasia User ID", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Trading Password", "required": True},
    ],
    "has_additional_params": True,
    "additional_params_fields": [
        {"key": "totp_secret", "label": "TOTP Secret", "placeholder": "Base32 TOTP secret (optional)", "required": False},
        {"key": "vendor_code", "label": "Vendor Code", "placeholder": "Vendor code (default: SHOONYA_ABHI_11)", "required": False},
    ],
    "instructions": "1. Enable TOTP in Finvasia App\n2. Enter User ID & Password\n3. Enter TOTP Secret\n4. System will authenticate via Noren protocol",
    "oauth_available": False,
})

_register_broker_meta("flattrade", {
    "display_name": "Flattrade",
    "auth_type": "credentials",
    "description": "Login with Flattrade credentials + TOTP",
    "fields": [
        {"key": "client_code", "label": "User ID", "placeholder": "Flattrade User ID", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Trading Password", "required": True},
    ],
    "has_additional_params": True,
    "additional_params_fields": [
        {"key": "totp_secret", "label": "TOTP Secret", "placeholder": "Base32 TOTP secret (optional)", "required": False},
    ],
    "instructions": "1. Enable TOTP in Flattrade App\n2. Enter User ID & Password\n3. Enter TOTP Secret\n4. System will authenticate via Noren protocol",
    "oauth_available": False,
})

_register_broker_meta("groww", {
    "display_name": "Groww",
    "auth_type": "credentials",
    "description": "Login with Groww phone + OTP (no official API — uses reverse-engineered endpoints)",
    "fields": [
        {"key": "phone", "label": "Phone Number", "placeholder": "+91 9XXXXXXXXX", "required": True},
        {"key": "otp", "label": "OTP", "type": "password", "placeholder": "6-digit OTP (after sending via phone)", "required": False},
    ],
    "has_additional_params": False,
    "instructions": "1. Enter your registered Groww phone number\n2. Call authenticate to receive OTP\n3. Enter OTP to complete login\n4. Subsequent calls reuse the session token",
    "oauth_available": False,
})

_register_broker_meta("kotakneo", {
    "display_name": "Kotak Neo",
    "auth_type": "credentials",
    "description": "Connect via Kotak Neo Trade API (Consumer Key + TOTP + MPIN)",
    "oauth_available": False,
    "credential_login": True,
    "fields": [
        {"key": "consumer_key", "label": "Consumer Key (API access token)", "placeholder": "Neo app → More → Trade API → Generate application", "required": True},
        {"key": "mobile_number", "label": "Registered Mobile", "placeholder": "+919999999999", "required": True},
        {"key": "ucc", "label": "UCC (Client Code)", "placeholder": "e.g. AB1234", "required": True},
        {"key": "totp", "label": "TOTP (6-digit)", "placeholder": "From authenticator app", "required": True},
        {"key": "mpin", "label": "MPIN", "type": "password", "placeholder": "6-digit trading MPIN", "required": True},
    ],
    "has_additional_params": True,
    "instructions": "1. Neo app → More → Trade API → Generate application → copy Consumer Key\n2. Register TOTP (authenticator app)\n3. Enter Consumer Key + mobile + UCC + current TOTP + MPIN to connect",
})

_register_broker_meta("lemonn", {
    "display_name": "Lemonn",
    "auth_type": "credentials",
    "description": "Save your Lemonn credentials now — live trading activates when Lemonn launches its public API",
    "fields": [
        {"key": "client_code", "label": "Client ID", "placeholder": "Your Lemonn Client ID / Mobile", "required": True},
        {"key": "secret_key", "label": "Password / PIN", "type": "password", "placeholder": "Your Lemonn Password or PIN", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Lemonn has NOT launched a public trading API yet\n2. Save your Client ID + Password now to pre-connect your account\n3. Credentials are stored encrypted and activated automatically once the API is available",
    "oauth_available": False,
})

_register_broker_meta("hdfc", {
    "display_name": "HDFC Securities",
    "auth_type": "credentials",
    "description": "Save your HDFC Securities credentials now — live trading activates when HDFC Securities launches its public API",
    "fields": [
        {"key": "client_code", "label": "Client ID", "placeholder": "Your HDFC Securities Client ID", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Your HDFC Securities Password", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. HDFC Securities has NOT launched a public trading API yet\n2. Save your Client ID + Password now to pre-connect your account\n3. Credentials are stored encrypted and activated automatically once the API is available",
    "oauth_available": False,
})

_register_broker_meta("iifl", {
    "display_name": "IIFL Securities",
    "auth_type": "credentials",
    "description": "Save your IIFL Securities credentials now — live trading activates when IIFL Securities launches its public API",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Your IIFL Securities Client Code", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Your IIFL Securities Password", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. IIFL Securities has NOT launched a public trading API yet\n2. Save your Client Code + Password now to pre-connect your account\n3. Credentials are stored encrypted and activated automatically once the API is available",
    "oauth_available": False,
})

_register_broker_meta("motilal", {
    "display_name": "Motilal Oswal",
    "auth_type": "credentials",
    "description": "Save your Motilal Oswal credentials now — live trading activates when Motilal Oswal launches its public API",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Your Motilal Oswal Client Code", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Your Motilal Oswal Password", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Motilal Oswal has NOT launched a public trading API yet\n2. Save your Client Code + Password now to pre-connect your account\n3. Credentials are stored encrypted and activated automatically once the API is available",
    "oauth_available": False,
})

_register_broker_meta("geojit", {
    "display_name": "Geojit",
    "auth_type": "credentials",
    "description": "Save your Geojit credentials now — live trading activates when Geojit launches its public API",
    "fields": [
        {"key": "client_code", "label": "Client ID", "placeholder": "Your Geojit Client ID", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Your Geojit Password", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Geojit has NOT launched a public trading API yet\n2. Save your Client ID + Password now to pre-connect your account\n3. Credentials are stored encrypted and activated automatically once the API is available",
    "oauth_available": False,
})

_register_broker_meta("reliance", {
    "display_name": "Reliance Securities",
    "auth_type": "credentials",
    "description": "Save your Reliance Securities credentials now — live trading activates when Reliance Securities launches its public API",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Your Reliance Securities Client Code", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Your Reliance Securities Password", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Reliance Securities has NOT launched a public trading API yet\n2. Save your Client Code + Password now to pre-connect your account\n3. Credentials are stored encrypted and activated automatically once the API is available",
    "oauth_available": False,
})

_register_broker_meta("axis", {
    "display_name": "Axis Securities",
    "auth_type": "credentials",
    "description": "Save your Axis Securities credentials now — live trading activates when Axis Securities launches its public API",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Your Axis Securities Client Code", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Your Axis Securities Password", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Axis Securities has NOT launched a public trading API yet\n2. Save your Client Code + Password now to pre-connect your account\n3. Credentials are stored encrypted and activated automatically once the API is available",
    "oauth_available": False,
})

_register_broker_meta("binance", {
    "display_name": "Binance",
    "auth_type": "credentials",
    "description": "Save your Binance credentials now — live trading activates when the crypto integration is certified",
    "fields": [
        {"key": "api_key", "label": "API Key", "placeholder": "Your Binance API Key", "required": True},
        {"key": "secret_key", "label": "API Secret", "type": "password", "placeholder": "Your Binance API Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Binance has a public REST API but is not activated in this India-focused platform\n2. Save your API Key + Secret now to pre-connect your account\n3. Credentials are stored encrypted and activated once the integration is certified",
    "oauth_available": False,
})

_register_broker_meta("bybit", {
    "display_name": "Bybit",
    "auth_type": "credentials",
    "description": "Save your Bybit credentials now — live trading activates when the crypto integration is certified",
    "fields": [
        {"key": "api_key", "label": "API Key", "placeholder": "Your Bybit API Key", "required": True},
        {"key": "secret_key", "label": "API Secret", "type": "password", "placeholder": "Your Bybit API Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Bybit has a public REST API but is not activated in this India-focused platform\n2. Save your API Key + Secret now to pre-connect your account\n3. Credentials are stored encrypted and activated once the integration is certified",
    "oauth_available": False,
})

_register_broker_meta("okx", {
    "display_name": "OKX",
    "auth_type": "credentials",
    "description": "Save your OKX credentials now — live trading activates when the crypto integration is certified",
    "fields": [
        {"key": "api_key", "label": "API Key", "placeholder": "Your OKX API Key", "required": True},
        {"key": "secret_key", "label": "API Secret", "type": "password", "placeholder": "Your OKX API Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. OKX has a public REST API but is not activated in this India-focused platform\n2. Save your API Key + Secret now to pre-connect your account\n3. Credentials are stored encrypted and activated once the integration is certified",
    "oauth_available": False,
})

_register_broker_meta("oanda", {
    "display_name": "OANDA",
    "auth_type": "credentials",
    "description": "Save your OANDA credentials now — live trading activates when the forex integration is certified",
    "fields": [
        {"key": "api_key", "label": "API Key", "placeholder": "Your OANDA API Key", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. OANDA has a public API for forex/CFD but is not activated in this India-focused platform\n2. Save your API Key now to pre-connect your account\n3. Credentials are stored encrypted and activated once the integration is certified",
    "oauth_available": False,
})

_register_broker_meta("interactive_brokers", {
    "display_name": "Interactive Brokers",
    "auth_type": "credentials",
    "description": "Save your Interactive Brokers credentials now — live trading activates when the global broker integration is certified",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Your Interactive Brokers Client Code", "required": True},
        {"key": "secret_key", "label": "Password / Secret", "type": "password", "placeholder": "Your Interactive Brokers Password or Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Interactive Brokers offers a global API (TWS / Client Portal) but is not activated in this India-focused platform\n2. Save your Client Code + Secret now to pre-connect your account\n3. Credentials are stored encrypted and activated once the integration is certified",
    "oauth_available": False,
})

_register_broker_meta("alpaca", {
    "display_name": "Alpaca",
    "auth_type": "credentials",
    "description": "Save your Alpaca credentials now — live trading activates when the US-broker integration is certified",
    "fields": [
        {"key": "api_key", "label": "API Key", "placeholder": "Your Alpaca API Key", "required": True},
        {"key": "secret_key", "label": "API Secret", "type": "password", "placeholder": "Your Alpaca API Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Alpaca has a public API for US stocks but is not activated in this India-focused platform\n2. Save your API Key + Secret now to pre-connect your account\n3. Credentials are stored encrypted and activated once the integration is certified",
    "oauth_available": False,
})

_register_broker_meta("icici", {
    "display_name": "ICICI Direct",
    "auth_type": "credentials",
    "description": "Save your ICICI Direct credentials — public API pending",
    "fields": [
        {"key": "client_code", "label": "Client Code", "placeholder": "Your ICICI Direct Client Code", "required": True},
        {"key": "secret_key", "label": "Password", "type": "password", "placeholder": "Your ICICI Direct Password", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. ICICI Direct does not yet offer a public trading API\n2. Save your credentials now to pre-connect\n3. Activated automatically once API is available",
    "oauth_available": False,
})


def get_broker_metadata(broker: str | None = None) -> list[dict] | dict:
    """Legacy facade — data now lives in the Unified Broker SDK v2 registry.

    BROKER_METADATA above remains as the authored UI copy; the SDK registry
    (populated from it by brokers/__init__) is the single source of truth and
    additionally carries adapter classes + capability sets.
    """

    from brokers.sdk.registry import registry

    return registry.metadata(broker)

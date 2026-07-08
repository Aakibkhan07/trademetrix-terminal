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

_register_broker_meta("kotakneo", {
    "display_name": "Kotak Neo",
    "auth_type": "api_key_secret",
    "description": "Connect via Kotak Neo API Key & Secret",
    "fields": [
        {"key": "client_id", "label": "Consumer Key", "placeholder": "Kotak Neo Consumer Key", "required": True},
        {"key": "secret_key", "label": "Consumer Secret", "type": "password", "placeholder": "Kotak Neo Consumer Secret", "required": True},
    ],
    "has_additional_params": False,
    "instructions": "1. Go to developer.kotakneo.com\n2. Create an application\n3. Copy Consumer Key & Secret here\n4. System will obtain access token automatically",
    "oauth_available": False,
})


def get_broker_metadata(broker: str | None = None) -> list[dict] | dict:
    if broker:
        data = BROKER_METADATA.get(broker)
        if not data:
            raise ValueError(f"Unknown broker: {broker}")
        return {"broker": broker, **data}
    return [{"broker": k, **v} for k, v in BROKER_METADATA.items()]

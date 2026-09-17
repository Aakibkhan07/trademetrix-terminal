import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import httpx

from application.services.broker_service import BrokerService
from brokers import list_brokers
from brokers.registry import get_broker_metadata
from core.config import settings
from core.deps import get_current_user, require_admin
from core.db import get_supabase
from core.models import UserProfile
from core.safe_query import safe_single
from core.security import decrypt_broker_credentials
from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/brokers", tags=["brokers"])

_broker_service = BrokerService(SupabaseBrokerRepository())


class BrokerCredentialInput(BaseModel):
    broker: str
    api_key: str = ""
    secret_key: str = ""
    client_id: str = ""
    client_code: str = ""
    access_token: str = ""
    additional_params: dict = {}


class BrokerCredentialResponse(BaseModel):
    id: str
    broker: str
    is_active: bool


class ActivateBrokerRequest(BaseModel):
    broker: str


class AuthCodeInput(BaseModel):
    auth_code: str


def _frontend_url() -> str:
    return f"{settings.frontend_url or 'https://ai.trademetrix.tech'}/brokers"


@router.get("/list")
async def list_available_brokers():
    return {"brokers": list_brokers()}


@router.get("/metadata")
async def list_broker_metadata():
    return {"brokers": get_broker_metadata()}


@router.get("/metadata/{broker}")
async def broker_metadata(broker: str):
    try:
        return get_broker_metadata(broker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/credentials")
async def get_credentials(current_user: UserProfile = Depends(get_current_user)):
    credentials = await _broker_service.list_credentials(current_user.id)
    return {"credentials": credentials}


@router.post("/activate")
async def activate_broker(req: ActivateBrokerRequest, current_user: UserProfile = Depends(get_current_user)):
    ok = await _broker_service.activate_broker(current_user.id, req.broker)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No credentials found for broker '{req.broker}'")
    return {"message": f"Broker '{req.broker}' activated", "broker": req.broker}


@router.post("/credentials", status_code=201)
async def save_credentials(req: BrokerCredentialInput, current_user: UserProfile = Depends(get_current_user)):
    api_key = req.api_key or req.client_id or req.client_code or ""
    try:
        cred = await _broker_service.save_credentials(
            current_user.id, req.broker, api_key, req.secret_key,
            access_token=req.access_token or None,
            additional_params=req.additional_params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        from application.services.analytics_service import AnalyticsService
        await AnalyticsService().record_server_event(
            current_user.id, "broker.connected", {"broker": req.broker}
        )
    except Exception:
        pass
    return BrokerCredentialResponse(id=cred.id, broker=cred.broker, is_active=cred.is_active)


@router.delete("/credentials/{broker_name}", status_code=204)
async def delete_credentials(broker_name: str, current_user: UserProfile = Depends(get_current_user)):
    ok = await _broker_service.delete_credentials(current_user.id, broker_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Credentials not found")


@router.post("/{broker}/re-auth")
async def broker_re_auth(broker: str, current_user: UserProfile = Depends(get_current_user)):
    try:
        auth_url = await _broker_service.re_auth(current_user.id, broker)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{broker}/auth-url")
async def broker_auth_url(broker: str, current_user: UserProfile = Depends(get_current_user)):
    try:
        auth_url = await _broker_service.get_auth_url(current_user.id, broker)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{broker}/exchange-code")
async def broker_exchange_code(broker: str, req: AuthCodeInput, current_user: UserProfile = Depends(get_current_user)):
    try:
        msg = await _broker_service.exchange_code(current_user.id, broker, req.auth_code)
        return {"message": msg}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{broker}/callback")
async def broker_callback(broker: str, code: str = Query(None, alias="auth_code"), state: str | None = Query(None)):
    from urllib.parse import quote
    query_code = code
    if not query_code:
        query_code = state
    success, msg = await _broker_service.handle_callback(broker, query_code, state)
    if success:
        return RedirectResponse(url=f"{_frontend_url()}?auth_success=1")
    return RedirectResponse(url=f"{_frontend_url()}?auth_error={quote(msg)}")


@router.get("/admin/rate-limit")
async def broker_rate_limit_status(current_user: UserProfile = Depends(require_admin)):
    """Per-endpoint Fyers request rates + retry behavior (for limit compliance)."""
    from brokers.fyers_http import fyers_rate_snapshot
    return fyers_rate_snapshot()


_METRIC_KEYS = (
    "requests_total",
    "success_rate",
    "failure_rate",
    "retry_total",
    "token_refresh_total",
    "order_latency_ms",
    "rest_latency_ms",
    "websocket_latency_ms",
    "cache_hit_ratio",
    "dedup_hit_ratio",
    "rate_limit_utilization",
)


def _capability_report(broker: str) -> dict:
    from brokers.sdk import capabilities
    return capabilities.get_capabilities(broker).to_dict()


def _health_report(broker: str) -> dict:
    """Unified per-broker health payload (auth/rest/ws/circuit/rate/caps)."""
    from brokers.sdk.health import default_health_service
    from brokers.sdk.auth import default_session_manager

    health = default_health_service.get(broker)
    session_health = next(
        (s.health() for s in default_session_manager.sessions() if s.provider.broker == broker),
        None,
    )
    return {
        "broker": broker,
        "authentication": {
            "ok": session_health.ok if session_health else (health.auth_ok if health else None),
            "state": (session_health.auth_state.value if session_health else "unregistered"),
            "reason": (session_health.reason if session_health else ""),
        },
        "rest_connectivity": bool(health.rest_healthy) if health else False,
        "websocket_connectivity": bool(health.ws_healthy) if health else False,
        "circuit_state": "open" if (health and health.circuit_open) else "closed",
        "rate_limit": {
            "budget_rpm": (health.components.get("rate_budget_rpm") if health else None),
            "used_last_minute": (health.components.get("rate_used_last_minute") if health else None),
        },
        "last_successful_request": health.components.get("last_success_at") if health else None,
        "last_failed_request": (health.components.get("last_failed_at") if health else None),
        "last_error": health.last_error if health else "",
        "capabilities": _capability_report(broker),
        "reported_at": round(health.updated_at, 3) if health else None,
    }


def _metric_report(broker: str) -> dict:
    from brokers.sdk.metrics import default_broker_metrics
    snap = default_broker_metrics.snapshot(broker)
    payload = snap.to_dict()
    payload["metrics"] = {k: payload["metrics"].get(k) for k in _METRIC_KEYS if k in payload["metrics"]}
    return payload


@router.get("/health")
async def brokers_health_status(current_user: UserProfile = Depends(get_current_user)):
    """Unified health for all known brokers (Phase 4 observability)."""
    from brokers.sdk.health import default_health_service
    brokers = list_brokers()
    report = {}
    for name in brokers:
        report[name] = _health_report(name)
    overall_healthy = all(
        d.get("rest_connectivity") or d.get("websocket_connectivity")
        for d in report.values()
    )
    return {"overall_healthy": overall_healthy, "brokers": report}


@router.get("/health/{broker}")
async def broker_health(broker: str, current_user: UserProfile = Depends(get_current_user)):
    if broker not in list_brokers():
        raise HTTPException(status_code=404, detail=f"Unknown broker '{broker}'")
    return _health_report(broker)


@router.get("/metrics/{broker}")
async def broker_metrics(broker: str, current_user: UserProfile = Depends(get_current_user)):
    if broker not in list_brokers():
        raise HTTPException(status_code=404, detail=f"Unknown broker '{broker}'")
    return _metric_report(broker)


@router.get("/capabilities")
async def broker_capabilities():
    """Runtime capability discovery (never a static table)."""
    from brokers.sdk.capabilities import get_capabilities
    return {"brokers": {name: get_capabilities(name).to_dict() for name in list_brokers()}}


# ── Zerodha Kite Connect (request_token flow — not OAuth) ──────────────────

ZERODHA_LOGIN_URL = "https://kite.trade/connect/login"
ZERODHA_REDIRECT_URI = settings.zerodha_redirect_uri or f"{settings.frontend_url or 'https://ai.trademetrix.tech'}/brokers/zerodha/callback"


@router.get("/zerodha/login-url")
async def zerodha_login_url(current_user: UserProfile = Depends(get_current_user)):
    supabase = get_supabase()
    cred = safe_single(
        supabase.table("broker_credentials")
        .select("encrypted_api_key")
        .eq("user_id", current_user.id)
        .eq("broker", "zerodha")
    )
    api_key = decrypt_broker_credentials(cred["encrypted_api_key"]) if cred else ""
    return {"login_url": f"{ZERODHA_LOGIN_URL}?api_key={api_key}"}


class ZerodhaRequestTokenInput(BaseModel):
    request_token: str


@router.post("/zerodha/exchange-request-token")
async def zerodha_exchange_request_token(
    req: ZerodhaRequestTokenInput,
    current_user: UserProfile = Depends(get_current_user),
):
    import httpx

    supabase = get_supabase()
    cred = safe_single(
        supabase.table("broker_credentials")
        .select("*")
        .eq("user_id", current_user.id)
        .eq("broker", "zerodha")
    )
    if not cred:
        raise HTTPException(status_code=400, detail="No Zerodha credentials found. Save them first.")

    api_key = decrypt_broker_credentials(cred["encrypted_api_key"])
    secret_key = decrypt_broker_credentials(cred["encrypted_secret_key"])

    from core.http_client import get_http_client

    client = await get_http_client()
    resp = await client.post(
        "https://api.kite.trade/session/token",
        data={
            "api_key": api_key,
            "request_token": req.request_token,
            "checksum": api_key + req.request_token + secret_key,
        },
        headers={"X-Kite-Version": "3"},
        timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
    )
    data = resp.json()
    if data.get("status") == "error":
        raise HTTPException(status_code=400, detail=f"Zerodha auth failed: {data.get('message', '')}")

    access_token = data["data"]["access_token"]
    encrypted = encrypt_broker_credentials(access_token)
    supabase.table("broker_credentials").update(
        {"encrypted_access_token": encrypted, "is_active": True}
    ).eq("id", cred["id"]).execute()

    return {"message": "Zerodha authenticated successfully!"}


@router.get("/zerodha/callback")
async def zerodha_callback(
    request_token: str = Query(alias="request_token"),
    state: str | None = Query(None),
):
    import httpx
    from urllib.parse import quote

    FRONTEND_URL = ZERODHA_REDIRECT_URI.rsplit("/", 1)[0]  # strip /callback → base URL
    user_id = state or ""

    supabase = get_supabase()
    cred = safe_single(
        supabase.table("broker_credentials")
        .select("*")
        .eq("user_id", user_id)
        .eq("broker", "zerodha")
    )
    if not cred:
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=No+Zerodha+credentials+found")

    api_key = decrypt_broker_credentials(cred["encrypted_api_key"])
    secret_key = decrypt_broker_credentials(cred["encrypted_secret_key"])

    from core.http_client import get_http_client

    client = await get_http_client()
    resp = await client.post(
        "https://api.kite.trade/session/token",
        data={
            "api_key": api_key,
            "request_token": request_token,
            "checksum": api_key + request_token + secret_key,
        },
        headers={"X-Kite-Version": "3"},
        timeout=httpx.Timeout(settings.broker_request_timeout, connect=settings.broker_connect_timeout),
    )
    data = resp.json()
    if data.get("status") == "error":
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=Zerodha+auth+failed")

    access_token = data["data"]["access_token"]
    encrypted = encrypt_broker_credentials(access_token)
    supabase.table("broker_credentials").update(
        {"encrypted_access_token": encrypted, "is_active": True}
    ).eq("id", cred["id"]).execute()

    return RedirectResponse(url=f"{FRONTEND_URL}?auth_success=1")

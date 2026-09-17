"""User portal aggregation endpoint — single call for the user dashboard."""

from fastapi import APIRouter, Depends
from core.deps import get_current_user, get_capabilities
from core.capabilities import Capabilities
from core.models import UserProfile

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/me")
async def get_user_portal(
    current_user: UserProfile = Depends(get_current_user),
    caps: Capabilities = Depends(get_capabilities),
):
    """Return everything the user portal needs in one call:
    profile, subscription tier, capabilities, assigned strategies,
    broker connections.
    """
    from application.services.strategy_catalog_service import StrategyCatalogService
    from application.services.broker_service import BrokerService
    from infrastructure.repositories.broker_repository import SupabaseBrokerRepository

    strat_svc = StrategyCatalogService()
    broker_svc = BrokerService(SupabaseBrokerRepository())

    strategies = await strat_svc.get_assigned_strategies(current_user.id, caps)
    credentials = await broker_svc.list_credentials(current_user.id)

    tier_map = {
        "free": "Free",
        "starter": "Starter",
        "pro": "Pro",
        "enterprise": "Enterprise",
    }

    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "phone": current_user.phone,
            "subscription_tier": current_user.subscription_tier or "free",
            "is_admin": current_user.is_admin,
            "created_at": current_user.created_at,
        },
        "plan": {
            "tier": current_user.subscription_tier or "free",
            "tier_label": tier_map.get(current_user.subscription_tier or "free", "Free"),
            "capabilities": caps.model_dump(),
        },
        "strategies": strategies,
        "brokers": {
            "connections": credentials,
            "count": len(credentials),
            "active_count": sum(1 for c in credentials if c.get("is_active", False)),
        },
    }

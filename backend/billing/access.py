from django.conf import settings
from django.utils import timezone

from .exceptions import SubscriptionRequired
from .models import Subscription


def get_access(company_id):
    if not settings.BILLING_ENABLED:
        return {"enabled": False, "has_access": True, "exempt": False, "status": "disabled"}
    subscription = Subscription.objects.filter(company_id=company_id).first()
    if subscription is None:
        return {"enabled": True, "has_access": False, "exempt": False, "status": "none"}
    active = (subscription.livemode is settings.STRIPE_LIVE_MODE and subscription.status in {"active", "trialing"} and subscription.access_until is not None
              and subscription.access_until > timezone.now())
    return {"enabled": True, "has_access": subscription.exempt or active,
            "exempt": subscription.exempt, "status": subscription.status}


def require_access(company_id):
    if not get_access(company_id)["has_access"]:
        raise SubscriptionRequired()

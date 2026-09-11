"""Abonnements Azula distincts des factures et règlements métier des sociétés."""
import hashlib
import re
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from erp.models import AuditEvent, Company, User

from . import provider
from .access import get_access
from .exceptions import BillingError
from .models import CheckoutAttempt, Plan, Subscription, WebhookEvent

FINAL_STATUSES = {"none", "canceled", "incomplete_expired"}
STATUSES = FINAL_STATUSES | {"active", "trialing", "past_due", "unpaid", "incomplete", "paused"}
ZERO_DECIMAL = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "VND", "VUV", "XAF", "XOF", "XPF"}
THREE_DECIMAL = {"BHD", "JOD", "KWD", "OMR", "TND"}


def configured():
    parsed = urlsplit(settings.BILLING_PUBLIC_URL)
    local = not settings.STRIPE_LIVE_MODE and parsed.hostname in {"localhost", "127.0.0.1"}
    valid_url = (parsed.scheme == "https" or (parsed.scheme == "http" and local)) and bool(parsed.hostname)
    return bool(valid_url and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                and parsed.path in {"", "/"} and settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET)


def identifier(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r"[A-Za-z0-9_]{1,90}", value):
        raise BillingError("billing_invalid_event")
    return value


def call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except provider.ProviderError as exc:
        raise BillingError(exc.code, 503 if exc.code == "billing_unavailable" else 400) from None


def timestamp(value, optional=False):
    if value is None and optional:
        return None
    if type(value) is not int or not 0 < value < 253402300800:
        raise BillingError("billing_invalid_event")
    return datetime.fromtimestamp(value, dt_timezone.utc)


def _admin(company_id, actor):
    user = User.objects.get(pk=actor.pk)
    if not user.is_active or user.company_id != company_id or user.role != "admin":
        raise BillingError("permission_denied", 403)
    return user


def _audit(company_id, action, actor=None, **metadata):
    AuditEvent.objects.create(company_id=company_id, actor=actor, actor_name=actor.username if actor else "Stripe",
                              action=action, object_type="subscription", object_id=str(company_id), metadata=metadata)


def plan_data(plan):
    return {"code": plan.code, "name": plan.name, "description": plan.description,
            "amount": format(plan.amount, f".{plan.precision}f"), "currency": plan.currency,
            "precision": plan.precision, "interval": plan.interval, "trial_days": plan.trial_days}


def overview(user):
    access = get_access(user.company_id)
    subscription = Subscription.objects.select_related("plan").filter(company_id=user.company_id).first()
    details = None
    if subscription and subscription.plan_id:
        details = {**plan_data(subscription.plan), "plan_code": subscription.plan.code,
                   "plan_name": subscription.plan.name, "current_period_end": subscription.current_period_end,
                   "trial_end": subscription.trial_end, "cancel_at_period_end": subscription.cancel_at_period_end}
    plans = [plan_data(plan) for plan in Plan.objects.filter(active=True, livemode=settings.STRIPE_LIVE_MODE)]
    if subscription and subscription.trial_used:
        for plan in plans:
            plan["trial_days"] = 0
    return {**access, "configured": configured(), "can_manage": user.role == "admin", "subscription": details,
            "plans": plans,
            "checkout_pending": CheckoutAttempt.objects.filter(company_id=user.company_id, status__in=["pending", "open"]).exists()}


def validate_price(price, plan=None):
    currency = price.get("currency", "").upper()
    amount = price.get("unit_amount")
    recurring = price.get("recurring") or {}
    if (not re.fullmatch(r"[A-Z]{3}", currency) or currency in {"ISK", "UGX"}
            or type(amount) is not int or amount <= 0 or amount > 999999999999
            or price.get("active") is not True or price.get("livemode") is not settings.STRIPE_LIVE_MODE
            or recurring.get("interval") not in {"month", "year"} or type(recurring.get("interval_count")) is not int or recurring.get("interval_count") != 1
            or recurring.get("usage_type") != "licensed" or price.get("billing_scheme") != "per_unit"
            or price.get("transform_quantity") or price.get("custom_unit_amount")):
        raise BillingError("billing_invalid_plan")
    try:
        if price.get("unit_amount_decimal") is not None and Decimal(str(price["unit_amount_decimal"])) != Decimal(amount):
            raise BillingError("billing_invalid_plan")
    except InvalidOperation:
        raise BillingError("billing_invalid_plan") from None
    precision = 0 if currency in ZERO_DECIMAL else 3 if currency in THREE_DECIMAL else 2
    exact = Decimal(amount).scaleb(-precision)
    if plan and (price.get("id") != plan.stripe_price_id or exact != plan.amount or currency != plan.currency
                 or precision != plan.precision or recurring["interval"] != plan.interval):
        raise BillingError("billing_invalid_plan")
    return {"amount": exact, "currency": currency, "precision": precision, "interval": recurring["interval"], "livemode": price["livemode"]}


def _session_details(session, attempt, subscription):
    if (session.get("id") != attempt.stripe_session_id or session.get("customer") != subscription.stripe_customer_id
            or session.get("mode") != "subscription" or session.get("metadata", {}).get("azula_company_id") != str(attempt.company_id)
            or session.get("metadata", {}).get("azula_checkout_attempt") != str(attempt.pk)):
        raise BillingError("billing_invalid_event")


def recover_checkout(company_id, actor):
    """Résout les réponses perdues sans recréer un abonnement possiblement payé."""
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=company_id)
        _admin(company_id, actor)
        attempt = CheckoutAttempt.objects.filter(company_id=company_id, status__in=["pending", "open"]).first()
        if not attempt:
            return
        subscription = Subscription.objects.get(company_id=company_id)
        if subscription.livemode is not settings.STRIPE_LIVE_MODE:
            raise BillingError("billing_mode_conflict", 409)
        remote = None
        if attempt.stripe_session_id:
            remote = call(provider.retrieve_checkout, attempt.stripe_session_id)
        elif attempt.expires_at <= timezone.now() and subscription.stripe_customer_id:
            remote = call(provider.find_checkout, subscription.stripe_customer_id, str(attempt.pk))
            if remote:
                attempt.stripe_session_id = identifier(remote.get("id"), "cs_")
                attempt.save(update_fields=["stripe_session_id"])
        if remote:
            _session_details(remote, attempt, subscription)
            if remote.get("status") == "complete":
                synchronize(subscription, remote.get("subscription"))
                return
            if remote.get("status") != "expired":
                return
        elif attempt.expires_at > timezone.now():
            return
        # L'horodatage envoyé à Stripe est figé à la réservation. Après cette
        # échéance, aucune création tardive de cette session n'est possible.
        attempt.status = "expired"
        attempt.save(update_fields=["status"])


def checkout(user, plan_code, key):
    if not settings.BILLING_ENABLED or not configured():
        raise BillingError("billing_unavailable", 503)
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
        raise BillingError("billing_idempotency_required")
    digest = hashlib.sha256(key.encode()).hexdigest()
    recover_checkout(user.company_id, user)
    # La réservation est persistée avant le réseau. Même après une réponse
    # perdue, la reprise réutilise exactement la même opération chez Stripe.
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=user.company_id)
        actor = _admin(company.pk, user)
        subscription, _ = Subscription.objects.get_or_create(company=company)
        if subscription.stripe_customer_id and subscription.livemode is not settings.STRIPE_LIVE_MODE:
            raise BillingError("billing_mode_conflict", 409)
        subscription.livemode = settings.STRIPE_LIVE_MODE
        if not subscription.customer_name:
            subscription.customer_name = company.name
            subscription.customer_email = company.email
        subscription.save(update_fields=["customer_name", "customer_email", "livemode", "updated_at"])
        plan = Plan.objects.filter(code=plan_code, active=True, livemode=settings.STRIPE_LIVE_MODE).first()
        if not plan:
            raise BillingError("billing_invalid_plan")
        if subscription.stripe_subscription_id and subscription.status not in FINAL_STATUSES:
            raise BillingError("billing_use_portal", 409)
        attempt = CheckoutAttempt.objects.filter(company=company, key_digest=digest).first()
        if attempt and attempt.plan_id != plan.pk:
            raise BillingError("idempotency_conflict", 409)
        if attempt and attempt.status in {"complete", "expired"}:
            raise BillingError("billing_checkout_finished", 409)
        pending = CheckoutAttempt.objects.filter(company=company, status__in=["pending", "open"]).first()
        if pending and pending != attempt:
            if pending.plan_id == plan.pk and pending.url and pending.expires_at > timezone.now():
                return {"url": pending.url}
            raise BillingError("billing_checkout_pending", 409)
        if not attempt:
            attempt = CheckoutAttempt.objects.create(company=company, plan=plan, key_digest=digest,
                trial_days=0 if subscription.trial_used else plan.trial_days,
                return_url=settings.BILLING_PUBLIC_URL,
                expires_at=(timezone.now() + timedelta(hours=1)).replace(microsecond=0))
            _audit(company.pk, "subscription.checkout_requested", actor, plan=plan.code)
        attempt_id = attempt.pk
    # Le client Stripe est confirmé dans sa propre transaction avant Checkout.
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=user.company_id)
        _admin(user.company_id, user)
        subscription = Subscription.objects.get(company_id=user.company_id)
        if not subscription.stripe_customer_id:
            customer = call(provider.create_customer, user.company_id, subscription.customer_name, subscription.customer_email,
                            f"azula-customer-{user.company_id}-{'live' if settings.STRIPE_LIVE_MODE else 'test'}")
            subscription.stripe_customer_id = identifier(customer.get("id"), "cus_")
            subscription.save(update_fields=["stripe_customer_id", "updated_at"])
    # Le verrou sérialise aussi les callbacks et demandes de deux administrateurs.
    # Aucun montant, client Stripe ou URL de retour n'est accepté du navigateur.
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=user.company_id)
        _admin(company.pk, user)
        subscription = Subscription.objects.get(company=company)
        attempt = CheckoutAttempt.objects.select_related("plan").get(pk=attempt_id)
        if subscription.stripe_subscription_id and subscription.status not in FINAL_STATUSES:
            raise BillingError("billing_use_portal", 409)
        if attempt.status not in {"pending", "open"}:
            raise BillingError("billing_checkout_finished", 409)
        if attempt.expires_at <= timezone.now():
            raise BillingError("billing_checkout_pending", 409)
        if attempt.url:
            return {"url": attempt.url}
        validate_price(call(provider.retrieve_price, attempt.plan.stripe_price_id), attempt.plan)
        session = call(provider.create_checkout, subscription.stripe_customer_id, attempt.plan.stripe_price_id,
            company.pk, attempt.return_url + "/subscription?checkout=success",
            attempt.return_url + "/subscription?checkout=cancelled", f"azula-checkout-{attempt.pk}-{digest}",
            trial_days=attempt.trial_days, expires_at=int(attempt.expires_at.timestamp()), checkout_reference=str(attempt.pk))
        attempt.stripe_session_id = identifier(session.get("id"), "cs_")
        _session_details(session, attempt, subscription)
        if session.get("status") != "open" or timestamp(session.get("expires_at")) != attempt.expires_at:
            raise BillingError("billing_invalid_event")
        attempt.url = session["url"]
        attempt.status = "open"
        attempt.save(update_fields=["stripe_session_id", "url", "status"])
        return {"url": attempt.url}


def portal(user):
    if not configured():
        raise BillingError("billing_unavailable", 503)
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=user.company_id)
        _admin(user.company_id, user)
        subscription = Subscription.objects.filter(company_id=user.company_id).first()
        if not subscription or not subscription.stripe_customer_id:
            raise BillingError("billing_no_subscription")
        if subscription.livemode is not settings.STRIPE_LIVE_MODE:
            raise BillingError("billing_mode_conflict", 409)
        result = call(provider.create_portal, subscription.stripe_customer_id, settings.BILLING_PUBLIC_URL + "/subscription")
        return {"url": result["url"]}


def _subscription_reference(obj, kind):
    if kind.startswith("customer.subscription."):
        return obj.get("id")
    if kind.startswith("checkout.session."):
        return obj.get("subscription")
    if kind.startswith("invoice."):
        parent = obj.get("parent")
        if isinstance(parent, dict) and parent.get("type") == "subscription_details":
            details = parent.get("subscription_details")
            return details.get("subscription") if isinstance(details, dict) else None
        return None
    return None


def synchronize(subscription, subscription_id):
    """Lecture canonique sous verrou : l'ordre des événements ne fait pas foi."""
    remote = call(provider.retrieve_subscription, identifier(subscription_id, "sub_"))
    if (remote.get("id") != subscription_id or remote.get("customer") != subscription.stripe_customer_id
            or remote.get("metadata", {}).get("azula_company_id") != str(subscription.company_id)):
        raise BillingError("billing_invalid_event")
    items = remote.get("items", {}).get("data", [])
    if len(items) != 1 or type(items[0].get("quantity")) is not int or items[0].get("quantity") != 1 or remote.get("items", {}).get("has_more"):
        raise BillingError("billing_invalid_plan")
    item = items[0]
    price_id = (item.get("price") or {}).get("id")
    plan = Plan.objects.filter(stripe_price_id=price_id, livemode=settings.STRIPE_LIVE_MODE).first()
    if not plan or remote.get("status") not in STATUSES - {"none"}:
        raise BillingError("billing_invalid_plan")
    # Un ancien abonnement ne peut pas écraser un abonnement plus récent.
    authorized_trial_days = 0
    if subscription.stripe_subscription_id != subscription_id:
        if subscription.stripe_subscription_id and subscription.status not in FINAL_STATUSES:
            raise BillingError("billing_subscription_conflict", 409)
        pending = CheckoutAttempt.objects.filter(company_id=subscription.company_id, plan=plan,
                                                 status__in=["pending", "open"]).first()
        if not pending or not pending.stripe_session_id:
            raise BillingError("billing_checkout_pending", 503)
        session = call(provider.retrieve_checkout, pending.stripe_session_id)
        _session_details(session, pending, subscription)
        if session.get("status") != "complete" or session.get("subscription") != subscription_id:
            raise BillingError("billing_checkout_pending", 503)
        pending.status = "complete"
        authorized_trial_days = pending.trial_days
        pending.save(update_fields=["status"])
    previous_trial_end = subscription.trial_end
    subscription.plan = plan
    subscription.stripe_subscription_id = subscription_id
    subscription.status = remote["status"]
    subscription.current_period_end = timestamp(item.get("current_period_end"))
    subscription.trial_end = timestamp(remote.get("trial_end"), optional=True)
    subscription.cancel_at_period_end = remote.get("cancel_at_period_end") is True
    subscription.access_until = None
    if remote["status"] == "trialing" and subscription.trial_end:
        if subscription.trial_used:
            if not previous_trial_end or subscription.trial_end > previous_trial_end:
                raise BillingError("billing_invalid_event")
        elif not authorized_trial_days or (subscription.trial_end - timestamp(remote.get("trial_start"))).total_seconds() > authorized_trial_days * 86400 + 60:
            raise BillingError("billing_invalid_event")
        subscription.access_until = min(subscription.trial_end, subscription.current_period_end)
        subscription.trial_used = True
    elif remote["status"] == "active":
        invoice = remote.get("latest_invoice")
        if (isinstance(invoice, dict) and invoice.get("status") == "paid" and type(invoice.get("amount_remaining")) is int and invoice.get("amount_remaining") == 0
                and invoice.get("customer") == subscription.stripe_customer_id
                and _subscription_reference(invoice, "invoice.paid") == subscription_id):
            subscription.access_until = subscription.current_period_end
    if subscription.access_until and subscription.access_until > timezone.now():
        subscription.exempt = False
    subscription.save()
    _audit(subscription.company_id, "subscription.synchronized", status=subscription.status,
           plan=plan.code, cancel_at_period_end=subscription.cancel_at_period_end)


def process_event(event, raw_body):
    event_id = identifier(event.get("id"), "evt_")
    digest = hashlib.sha256(raw_body).hexdigest()
    kind = event.get("type", "")
    accepted = {"checkout.session.completed", "checkout.session.expired", "customer.subscription.created",
                "customer.subscription.updated", "customer.subscription.deleted", "invoice.paid", "invoice.payment_failed"}
    if kind not in accepted:
        return
    obj = event["data"]["object"]
    customer_id = obj.get("customer")
    subscription = Subscription.objects.filter(stripe_customer_id=customer_id, livemode=settings.STRIPE_LIVE_MODE).first() if isinstance(customer_id, str) and customer_id else None
    # Les événements d'autres applications du compte Stripe sont acquittés,
    # sans enregistrer leurs données ni créer une société dans Azula.
    if subscription is None:
        return
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=subscription.company_id)
        subscription.refresh_from_db()
        previous = WebhookEvent.objects.filter(event_id=event_id).first()
        if previous:
            if previous.digest != digest:
                raise BillingError("billing_invalid_event")
            return
        if kind == "checkout.session.expired":
            attempt = CheckoutAttempt.objects.filter(company_id=subscription.company_id, stripe_session_id=obj.get("id"), status__in=["pending", "open"]).first()
            if attempt:
                current = call(provider.retrieve_checkout, attempt.stripe_session_id)
                _session_details(current, attempt, subscription)
                if current.get("status") == "expired":
                    attempt.status = "expired"
                    attempt.save(update_fields=["status"])
        else:
            reference = _subscription_reference(obj, kind)
            if not reference:
                return
            synchronize(subscription, reference)
        WebhookEvent.objects.create(event_id=event_id, digest=digest, company_id=subscription.company_id, kind=kind)

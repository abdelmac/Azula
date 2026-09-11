from django.db import models
from django.db.models import Q


class Plan(models.Model):
    """Catalogue de l'opérateur Azula, jamais modifiable par un locataire."""
    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    stripe_price_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=22, decimal_places=6)
    currency = models.CharField(max_length=3)
    precision = models.PositiveSmallIntegerField(default=2)
    interval = models.CharField(max_length=5, choices=[("month", "month"), ("year", "year")])
    trial_days = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    livemode = models.BooleanField(default=False)

    class Meta:
        ordering = ["amount", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="billing_positive_amount"),
            models.CheckConstraint(condition=Q(precision__lte=3), name="billing_precision_range"),
            models.CheckConstraint(condition=Q(trial_days=0) | Q(trial_days__gte=2, trial_days__lte=90), name="billing_trial_range"),
            models.CheckConstraint(condition=Q(interval__in=["month", "year"]), name="billing_interval"),
        ]


class Subscription(models.Model):
    company = models.OneToOneField("erp.Company", on_delete=models.PROTECT)
    exempt = models.BooleanField(default=False)
    livemode = models.BooleanField(default=False)
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.PROTECT)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    customer_email = models.EmailField(blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=24, default="none")
    access_until = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    trial_used = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["stripe_customer_id"], condition=~Q(stripe_customer_id=""), name="billing_unique_customer"),
            models.UniqueConstraint(fields=["stripe_subscription_id"], condition=~Q(stripe_subscription_id=""), name="billing_unique_subscription"),
        ]


class CheckoutAttempt(models.Model):
    company = models.ForeignKey("erp.Company", on_delete=models.PROTECT)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    key_digest = models.CharField(max_length=64)
    stripe_session_id = models.CharField(max_length=100, blank=True)
    url = models.URLField(max_length=8192, blank=True)
    return_url = models.URLField(max_length=500)
    status = models.CharField(max_length=12, default="pending")
    trial_days = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "key_digest"], name="billing_checkout_idempotency"),
            models.UniqueConstraint(fields=["company"], condition=Q(status__in=["pending", "open"]), name="billing_one_open_checkout"),
            models.UniqueConstraint(fields=["stripe_session_id"], condition=~Q(stripe_session_id=""), name="billing_unique_checkout_session"),
        ]


class WebhookEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True)
    digest = models.CharField(max_length=64)
    company = models.ForeignKey("erp.Company", on_delete=models.PROTECT, null=True)
    kind = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

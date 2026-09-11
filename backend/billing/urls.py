from django.urls import path

from .api import CheckoutView, OverviewView, PortalView, WebhookView

urlpatterns = [
    path("", OverviewView.as_view(), name="billing-overview"),
    path("checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("portal/", PortalView.as_view(), name="billing-portal"),
    path("webhook/", WebhookView.as_view(), name="billing-webhook"),
]

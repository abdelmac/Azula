from django.urls import path
from rest_framework.routers import DefaultRouter

from .api import (
    BankAccountViewSet,
    BankTransactionViewSet,
    ExternalTransactionViewSet,
    ExternalView,
    IntegrationViewSet,
    KeyViewSet,
)

router = DefaultRouter()
router.register("integrations", IntegrationViewSet, basename="integration")
router.register("integration-keys", KeyViewSet, basename="integration-key")
router.register("bank-accounts", BankAccountViewSet, basename="bank-account")
router.register("bank-transactions", BankTransactionViewSet, basename="bank-transaction")
router.register("external-transactions", ExternalTransactionViewSet, basename="external-transaction")
urlpatterns = router.urls + [path(f"external/v1/{name}/", ExternalView.as_view(resource=name)) for name in ("schema", "catalog", "customers", "invoices", "transactions", "bank-transactions")]

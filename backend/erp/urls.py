from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("customers", api.CustomerViewSet, basename="customer")
router.register("products", api.ProductViewSet, basename="product")
router.register("product-categories", api.ProductCategoryViewSet, basename="product-category")
router.register("warehouses", api.WarehouseViewSet, basename="warehouse")
router.register("units", api.UnitViewSet, basename="unit")
router.register("invoices", api.InvoiceViewSet, basename="invoice")
router.register("accounts", api.AccountViewSet, basename="account")
router.register("journals", api.JournalViewSet, basename="journal")
router.register("periods", api.PeriodViewSet, basename="period")
router.register("entries", api.EntryViewSet, basename="entry")
router.register("audit", api.AuditViewSet, basename="audit")
router.register("users", api.UserViewSet, basename="user")

urlpatterns = [
    path("auth/csrf/", api.CsrfView.as_view(), name="csrf"),
    path("auth/login/", api.LoginView.as_view(), name="login"),
    path("auth/logout/", api.LogoutView.as_view(), name="logout"),
    path("auth/me/", api.MeView.as_view(), name="me"),
    path("company/", api.CompanyView.as_view(), name="company"),
    path("trial-balance/", api.TrialBalanceView.as_view(), name="trial-balance"),
    path("", include(router.urls)),
]

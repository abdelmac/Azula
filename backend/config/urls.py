from django.contrib import admin
from django.urls import include, path, re_path

from erp.reporting import DashboardView, ExportView

from .views import health, spa

urlpatterns = [
    path("healthz/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/", include("erp.urls")),
    path("api/", include("connections.urls")),
    path("api/dashboard/", DashboardView.as_view(), name="dashboard"),
    path("api/export/", ExportView.as_view(), name="export"),
    re_path(r"^(?!api(?:/|$)|admin(?:/|$)|static/|assets/).*$", spa),
]

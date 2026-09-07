from django.contrib import admin
from django.urls import include, path, re_path

from .views import spa

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("erp.urls")),
    re_path(r"^(?!api(?:/|$)|admin(?:/|$)|static/|assets/).*$", spa),
]

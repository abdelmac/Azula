"""Inspection seule : toutes les mutations passent par les services et l'API."""

from django.contrib import admin

from .models import (
    Account,
    AuditEvent,
    Company,
    Customer,
    Entry,
    EntryLine,
    Invoice,
    InvoiceLine,
    Journal,
    Payment,
    Period,
    Product,
    User,
)


class InspectionAdmin(admin.ModelAdmin):
    actions = None
    list_per_page = 50

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if self.model is Company:
            return queryset.filter(pk=request.user.company_id)
        return queryset.filter(company_id=request.user.company_id)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff and request.user.role == "admin"

    def has_view_permission(self, request, obj=None):
        if not self.has_module_permission(request):
            return False
        return obj is None or (obj.pk if isinstance(obj, Company) else obj.company_id) == request.user.company_id

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_exclude(self, request, obj=None):
        if self.model is User:
            return ("password", "user_permissions", "groups")
        return super().get_exclude(request, obj)


for model in (Company, User, Customer, Product, Invoice, InvoiceLine, Payment, Account, Journal, Period, Entry, EntryLine, AuditEvent):
    admin.site.register(model, InspectionAdmin)

admin.site.site_header = "Azula — inspection"
admin.site.site_title = "Azula"

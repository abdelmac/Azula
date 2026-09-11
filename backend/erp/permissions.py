from rest_framework.permissions import BasePermission


class CompanyPermission(BasePermission):
    """Toute requête métier exige une société et un rôle autorisé au serveur."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.is_active or not user.company_id:
            return False
        roles = getattr(view, "action_roles", {}).get(getattr(view, "action", ""))
        if roles is None:
            roles = getattr(view, "allowed_roles", {"admin", "accountant", "sales", "viewer"})
        if user.role not in roles:
            return False
        if not getattr(view, "subscription_exempt", False):
            from billing.access import require_access

            require_access(user.company_id)
        return True

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "company_id", obj.pk if obj.__class__.__name__ == "Company" else None) == request.user.company_id


MANAGE_ROLES = {"admin", "accountant", "sales"}
FINANCE_ROLES = {"admin", "accountant"}
ADMIN_ROLES = {"admin"}

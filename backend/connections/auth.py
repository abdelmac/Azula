import hashlib
import re

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .models import IntegrationKey


def assert_key_active(key, scope=None):
    creator = key.creator
    if (key.revoked_at or key.expires_at <= timezone.now() or not key.integration.enabled
            or not creator.is_active or creator.role != "admin"
            or creator.company_id != key.company_id or key.integration.company_id != key.company_id):
        raise AuthenticationFailed()
    if scope and scope not in key.scopes:
        raise PermissionDenied()
    from billing.access import require_access

    require_access(key.company_id)


class IntegrationAuthentication(BaseAuthentication):
    """Authentification volontairement réservée aux vues externes versionnées."""

    def authenticate(self, request):
        if not request.path.startswith("/api/external/v1/"):
            raise AuthenticationFailed()
        parts = get_authorization_header(request).split()
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise AuthenticationFailed()
        try:
            token = parts[1].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationFailed() from None
        if not re.fullmatch(r"azula_[A-Za-z0-9_-]{43}", token):
            raise AuthenticationFailed()
        key = IntegrationKey.objects.select_related("creator", "creator__company", "integration").filter(digest=hashlib.sha256(token.encode()).hexdigest()).first()
        if key is None:
            raise AuthenticationFailed()
        assert_key_active(key)
        return key.creator, key

    def authenticate_header(self, request):
        return "Bearer"

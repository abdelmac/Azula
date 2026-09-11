from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from erp.permissions import CompanyPermission
from erp.serializers import StrictInputMixin

from . import provider, services
from .exceptions import BillingError


class CheckoutInput(StrictInputMixin, serializers.Serializer):
    plan_code = serializers.SlugField(max_length=60)


class EmptyInput(StrictInputMixin, serializers.Serializer):
    pass


class OverviewView(APIView):
    permission_classes = [IsAuthenticated, CompanyPermission]
    subscription_exempt = True

    def get(self, request):
        return Response(services.overview(request.user))


class CheckoutView(OverviewView):
    allowed_roles = {"admin"}

    def post(self, request):
        data = CheckoutInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.checkout(request.user, data.validated_data["plan_code"], request.headers.get("Idempotency-Key")))


class PortalView(OverviewView):
    allowed_roles = {"admin"}

    def post(self, request):
        data = EmptyInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.portal(request.user))


class WebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        body = request.body
        if len(body) > 1_048_576:
            raise BillingError("billing_invalid_event")
        event = services.call(provider.verify_event, body, request.headers.get("Stripe-Signature", ""))
        services.process_event(event, body)
        return Response({"received": True})

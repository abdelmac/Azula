from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import exceptions, mixins, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from erp.api import CompanyViewSet, StandardPagination
from erp.models import Company, Customer, Invoice, Product
from erp.permissions import ADMIN_ROLES, FINANCE_ROLES, CompanyPermission
from erp.serializers import DraftSerializer, InvoiceSerializer, StrictInputMixin
from erp.services import DomainError, _audit, save_draft

from .auth import IntegrationAuthentication, assert_key_active
from .models import SCOPES, BankAccount, BankTransaction, ExternalTransaction, Integration, IntegrationKey
from .serializers import (
    BankAccountSerializer,
    BankTransactionSerializer,
    CsvInput,
    ExternalTransactionSerializer,
    IntegrationSerializer,
    KeyInput,
    KeySerializer,
    ReconcileInput,
    TransactionInput,
)
from .services import external_write, import_bank_csv, issue_key, receive_transaction, reconcile_bank_transaction


class ManagedViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, CompanyViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]
    allowed_roles = ADMIN_ROLES
    search_fields = ["name"]
    ordering_fields = ["id", "name"]

    def _save(self, serializer):
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=self.request.user.company_id)
            if serializer.instance:
                serializer.instance = serializer.Meta.model.objects.select_for_update().get(pk=serializer.instance.pk, company=company)
            if isinstance(serializer, BankAccountSerializer):
                if serializer.validated_data.get("currency", company.currency) != company.currency:
                    raise DomainError("invalid_input")
                if serializer.instance and serializer.instance.transactions.exists():
                    for field in ("currency", "iban"):
                        if field in serializer.validated_data and serializer.validated_data[field] != getattr(serializer.instance, field):
                            raise DomainError("immutable")
            obj = serializer.save(company=company)
            _audit(company, self.request.user, "connection.updated", obj, {"fields": sorted(serializer.validated_data)})

    perform_create = _save
    perform_update = _save


class IntegrationViewSet(ManagedViewSet):
    queryset = Integration.objects.all()
    serializer_class = IntegrationSerializer

    @action(detail=False, methods=["get"])
    def schema(self, request):
        return Response(external_schema())


class KeyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CompanyViewSet):
    queryset = IntegrationKey.objects.all()
    serializer_class = KeySerializer
    allowed_roles = ADMIN_ROLES
    ordering_fields = ["id", "created_at"]
    ordering = ["-id"]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request):
        serializer = KeyInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        key, secret = issue_key(request.user.company, request.user, serializer.validated_data)
        response = Response({"key": KeySerializer(key).data, "secret": secret}, status=201)
        response["Cache-Control"] = "no-store"
        return response

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        if request.data:
            raise exceptions.ValidationError("invalid_input")
        with transaction.atomic():
            Company.objects.select_for_update().get(pk=request.user.company_id)
            key = self.get_object()
            if key.revoked_at is None:
                key.revoked_at = timezone.now()
                key.save(update_fields=["revoked_at"])
                _audit(request.user.company, request.user, "integration.key_revoked", key)
            return Response(KeySerializer(key).data)


class BankAccountViewSet(ManagedViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    allowed_roles = FINANCE_ROLES

    @action(detail=True, methods=["post"], url_path="import")
    def import_csv(self, request, pk=None):
        self.get_object()
        serializer = CsvInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(import_bank_csv(request.user.company, request.user, int(pk), serializer.validated_data))


class BankTransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CompanyViewSet):
    queryset = BankTransaction.objects.select_related("account", "invoice")
    serializer_class = BankTransactionSerializer
    allowed_roles = FINANCE_ROLES
    search_fields = ["external_id", "description", "reference"]
    ordering_fields = ["id", "date", "amount"]
    ordering = ["-date", "-id"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = self._related_filter(super().get_queryset(), "account", BankAccount)
        state = self.request.query_params.get("reconciled")
        if state is not None:
            if state not in {"true", "false"}:
                raise exceptions.ValidationError("invalid_input")
            queryset = queryset.filter(reconciled_at__isnull=state == "false")
        for name, lookup in (("date_from", "date__gte"), ("date_to", "date__lte")):
            if self.request.query_params.get(name):
                value = serializers.DateField().run_validation(self.request.query_params[name])
                queryset = queryset.filter(**{lookup: value})
        return queryset

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        total = queryset.aggregate(amount=Coalesce(Sum("amount"), Value(0), output_field=DecimalField(max_digits=30, decimal_places=6)))["amount"]
        return Response({"count": queryset.count(), "amount": format(total, ".6f"), "currency": request.user.company.currency})

    @action(detail=True, methods=["post"])
    def reconcile(self, request, pk=None):
        self.get_object()
        serializer = ReconcileInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = reconcile_bank_transaction(request.user.company, request.user, int(pk), serializer.validated_data["invoice"])
        return Response(BankTransactionSerializer(item).data)


class ExternalTransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CompanyViewSet):
    queryset = ExternalTransaction.objects.select_related("integration")
    serializer_class = ExternalTransactionSerializer
    allowed_roles = FINANCE_ROLES
    search_fields = ["external_id", "reference"]
    ordering_fields = ["id", "date", "created_at"]
    ordering = ["-id"]
    http_method_names = ["get", "head", "options"]


class ExternalCustomerInput(StrictInputMixin, serializers.ModelSerializer):
    """Contrat stable et restreint ; les champs internes restent hors API externe."""
    class Meta:
        model = Customer
        fields = ("name", "email", "address", "tax_id")


class ExternalCustomerOutput(ExternalCustomerInput):
    class Meta(ExternalCustomerInput.Meta):
        fields = ("id", *ExternalCustomerInput.Meta.fields)


def external_schema():
    return {
        "version": "1", "base_path": "/api/external/v1/", "authentication": "Authorization: Bearer <API_KEY>",
        "scopes": list(SCOPES), "write_header": "Idempotency-Key", "money": "decimal_string",
        "pagination": {"page": 1, "page_size": 50, "max_page_size": 100},
        "endpoints": [
            {"method": "GET", "path": "catalog/", "scope": "catalog:read"},
            {"method": "GET", "path": "customers/", "scope": "customers:read"},
            {"method": "POST", "path": "customers/", "scope": "customers:write", "example": {"name": "Client API", "email": "client@example.com"}},
            {"method": "GET", "path": "invoices/", "scope": "invoices:read"},
            {"method": "POST", "path": "invoices/", "scope": "invoices:write", "example": {"customer": 1, "issue_date": "2026-09-10", "due_date": "2026-10-10", "document_language": "fr", "lines": [{"description": "Prestation", "quantity": "1", "unit_price": "100.00", "tax_rate": "20"}]}},
            {"method": "GET", "path": "bank-transactions/", "scope": "banking:read"},
            {"method": "POST", "path": "transactions/", "scope": "transactions:write", "example": {"external_id": "transaction-001", "amount": "100.00", "currency": "EUR", "date": "2026-09-10", "reference": "Commande 001"}},
        ],
        "invoice_status_on_create": "draft", "transaction_status_on_create": "received",
        "bank_provider_connected": False, "outbound_transfers": False,
    }


class ExternalView(APIView):
    authentication_classes = [IntegrationAuthentication]
    permission_classes = [IsAuthenticated, CompanyPermission]
    allowed_roles = ADMIN_ROLES
    resource = ""
    read_scopes = {"catalog": "catalog:read", "customers": "customers:read", "invoices": "invoices:read", "bank-transactions": "banking:read"}

    def get(self, request):
        if self.resource == "schema":
            return Response(external_schema())
        scope = self.read_scopes.get(self.resource)
        if not scope:
            raise exceptions.MethodNotAllowed("GET")
        assert_key_active(request.auth, scope)
        company = request.user.company
        search = request.query_params.get("search", "")
        if len(search) > 128:
            raise exceptions.ValidationError("invalid_input")
        if self.resource == "catalog":
            queryset = Product.objects.filter(company=company, archived=False).order_by("id")
            if search:
                queryset = queryset.filter(name__icontains=search)
            # Pas de prix d'achat ou de données fournisseur sur le catalogue Web.
            queryset = queryset.values("id", "reference", "name", "unit_price", "tax_rate", "specifications", "image_url")
            serializer = None
        elif self.resource == "customers":
            queryset = Customer.objects.filter(company=company, archived=False).order_by("id")
            if search:
                queryset = queryset.filter(name__icontains=search)
            serializer = ExternalCustomerOutput
        elif self.resource == "invoices":
            queryset = Invoice.objects.filter(company=company).select_related("company", "customer").prefetch_related("lines", "payments").order_by("-id")
            if search:
                queryset = queryset.filter(number__icontains=search)
            serializer = InvoiceSerializer
        else:
            queryset = BankTransaction.objects.filter(company=company).select_related("account", "invoice").order_by("-date", "-id")
            serializer = BankTransactionSerializer
        pagination = StandardPagination()
        result = pagination.paginate_queryset(queryset, request)
        if serializer:
            result = serializer(result, many=True).data
        else:
            result = [{**row, "unit_price": format(row["unit_price"], ".6f"), "tax_rate": format(row["tax_rate"], ".4f")} for row in result]
        return pagination.get_paginated_response(result)

    def post(self, request):
        scope = {"customers": "customers:write", "invoices": "invoices:write", "transactions": "transactions:write"}.get(self.resource)
        if not scope:
            raise exceptions.MethodNotAllowed("POST")
        assert_key_active(request.auth, scope)
        serializer_class = {"customers": ExternalCustomerInput, "invoices": DraftSerializer, "transactions": TransactionInput}[self.resource]
        serializer = serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def operation(company, actor):
            if self.resource == "customers":
                customer = Customer.objects.create(company=company, **data)
                _audit(company, actor, "customer.created", customer, {"source": "api"})
                return {"id": customer.pk, **ExternalCustomerInput(customer).data}
            if self.resource == "invoices":
                return InvoiceSerializer(save_draft(company, actor, data)).data
            return ExternalTransactionSerializer(receive_transaction(company, request.auth.integration, data)).data

        result, replay = external_write(request.auth, scope + "/create", request.headers.get("Idempotency-Key"), request.data, operation)
        return Response(result, status=200 if replay else 201, headers={"Idempotency-Replayed": str(replay).lower()})

import hashlib
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import exceptions, filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.views import exception_handler as drf_exception_handler

from .models import (
    Account,
    AuditEvent,
    Company,
    Customer,
    Entry,
    EntryLine,
    Invoice,
    Journal,
    LoginAttempt,
    Period,
    Product,
    ProductCategory,
    Unit,
    User,
    Warehouse,
)
from .permissions import ADMIN_ROLES, FINANCE_ROLES, MANAGE_ROLES, CompanyPermission
from .serializers import (
    AccountSerializer,
    AuditSerializer,
    CompanySerializer,
    CustomerSerializer,
    DraftSerializer,
    DuplicateInvoiceSerializer,
    EntrySerializer,
    InvoiceSerializer,
    JournalSerializer,
    LanguageSerializer,
    LoginSerializer,
    MeSerializer,
    PaymentInputSerializer,
    PeriodSerializer,
    ProductCategorySerializer,
    ProductSerializer,
    UnitSerializer,
    UserSerializer,
    WarehouseSerializer,
    money,
)
from .services import (
    DomainError,
    configure_company,
    duplicate_invoice,
    preview_invoice,
    record_payment,
    save_draft,
    set_period,
    validate_invoice,
)

logger = logging.getLogger(__name__)


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        code = exc.code
        status = 404 if code == "not_found" else 403 if code == "permission_denied" else 409 if code in {"immutable", "already_validated", "idempotency_conflict", "configuration_locked"} else 400
        return Response({"code": code, "detail": code}, status=status)
    if isinstance(exc, (DjangoValidationError, IntegrityError)):
        return Response({"code": "invalid_input", "detail": "invalid_input"}, status=400)
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.error("Erreur API non traitée : %s", type(exc).__name__)
        return Response({"code": "server_error", "detail": "server_error"}, status=500)
    if isinstance(exc, exceptions.NotAuthenticated):
        code = "not_authenticated"
        response.status_code = 401
    elif isinstance(exc, exceptions.AuthenticationFailed):
        code = "invalid_credentials"
    elif isinstance(exc, exceptions.PermissionDenied):
        code = "csrf_failed" if str(exc.detail).startswith("CSRF Failed") else "permission_denied"
    elif isinstance(exc, exceptions.NotFound) or response.status_code == 404:
        code = "not_found"
    elif isinstance(exc, exceptions.Throttled):
        code = "rate_limited"
    else:
        code = "invalid_input"
        if isinstance(exc, exceptions.ValidationError) and "invalid_amount" in str(exc.detail):
            code = "invalid_amount"
    response.data = {"code": code, "detail": code}
    return response


def csrf_failure(request, reason=""):
    return JsonResponse({"code": "csrf_failed", "detail": "csrf_failed"}, status=403)


class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class StableOrderingFilter(filters.OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = list(super().get_ordering(request, queryset, view) or ["id"])
        if not any(value.lstrip("-") in {"id", "pk"} for value in ordering):
            ordering.append("id")
        return ordering


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        response = Response({"csrfToken": get_token(request)})
        response["Cache-Control"] = "no-store"
        return response


def _bucket(value, now):
    key = hashlib.sha256(value.encode("utf-8")).hexdigest()
    # get_or_create gère la course à l'insertion ; le verrou protège les compteurs.
    LoginAttempt.objects.get_or_create(key=key)
    bucket = LoginAttempt.objects.select_for_update().get(key=key)
    window = timedelta(seconds=getattr(settings, "LOGIN_WINDOW_SECONDS", 900))
    if now >= bucket.window_started + window:
        bucket.failures = 0
        bucket.window_started = now
        bucket.locked_until = None
        bucket.save(update_fields=["failures", "window_started", "locked_until"])
    return bucket


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = timezone.now()
        with transaction.atomic():
            # REMOTE_ADDR uniquement : aucun X-Forwarded-For fourni par le client.
            ip_bucket = _bucket("ip:" + request.META.get("REMOTE_ADDR", "unknown"), now)
            if ip_bucket.failures >= getattr(settings, "LOGIN_IP_MAX_FAILURES", 30):
                return self._limited()
            user_bucket = _bucket("user:" + data["username"].casefold(), now)
            if user_bucket.failures >= getattr(settings, "LOGIN_MAX_FAILURES", 8):
                # Une adresse qui insiste sur des comptes bloqués consomme son quota.
                self._fail(ip_bucket)
                return self._limited()
            user = authenticate(request, username=data["username"], password=data["password"])
            if user is None or not user.is_active:
                self._fail(ip_bucket)
                self._fail(user_bucket)
                return Response({"code": "invalid_credentials", "detail": "invalid_credentials"}, status=401)
            user_bucket.failures = 0
            user_bucket.locked_until = None
            user_bucket.save(update_fields=["failures", "locked_until"])
            login(request, user)
        response = Response(MeSerializer(user).data)
        response["Cache-Control"] = "no-store"
        return response

    def _fail(self, bucket):
        bucket.failures += 1
        bucket.locked_until = bucket.window_started + timedelta(seconds=getattr(settings, "LOGIN_WINDOW_SECONDS", 900))
        bucket.save(update_fields=["failures", "locked_until"])

    def _limited(self):
        response = Response({"code": "rate_limited", "detail": "rate_limited"}, status=429)
        response["Retry-After"] = str(getattr(settings, "LOGIN_WINDOW_SECONDS", 900))
        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated, CompanyPermission]

    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        serializer = LanguageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.language = serializer.validated_data["language"]
        request.user.save(update_fields=["language"])
        return Response(MeSerializer(request.user).data)


class CompanyView(APIView):
    permission_classes = [IsAuthenticated, CompanyPermission]

    def get(self, request):
        return Response(CompanySerializer(request.user.company).data)

    def patch(self, request):
        if request.user.role != "admin":
            raise exceptions.PermissionDenied()
        serializer = CompanySerializer(request.user.company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        company = configure_company(request.user.company, request.user, serializer.validated_data)
        return Response(CompanySerializer(company).data)


class CompanyViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, CompanyPermission]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, StableOrderingFilter]
    ordering = ["id"]
    lookup_value_regex = r"[0-9]{1,18}"

    def get_queryset(self):
        queryset = super().get_queryset().filter(company_id=self.request.user.company_id)
        if len(self.request.query_params.get("search", "")) > 128:
            raise exceptions.ValidationError("invalid_input")
        return queryset

    def _related_filter(self, queryset, field, model):
        value = self.request.query_params.get(field)
        if value is not None:
            if not value.isdecimal() or len(value) > 18:
                raise exceptions.ValidationError("invalid_input")
            obj = get_object_or_404(model, company_id=self.request.user.company_id, pk=value)
            queryset = queryset.filter(**{field + "_id": obj.pk})
        return queryset


class ReferenceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, CompanyViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]
    action_roles = {"create": MANAGE_ROLES, "partial_update": MANAGE_ROLES}
    search_fields = ["name"]
    ordering_fields = ["id", "name", "archived"]
    ordering = ["name", "id"]

    def get_queryset(self):
        queryset = super().get_queryset()
        archived = self.request.query_params.get("archived")
        if archived is not None:
            if archived not in {"true", "false"}:
                raise exceptions.ValidationError("invalid_input")
            queryset = queryset.filter(archived=archived == "true")
        return queryset

    def _save(self, serializer):
        with transaction.atomic():
            # Sérialise les modifications de références avec la validation financière.
            Company.objects.select_for_update().get(pk=self.request.user.company_id)
            if serializer.instance is not None:
                serializer.instance = type(serializer.instance).objects.select_for_update().get(pk=serializer.instance.pk, company=self.request.user.company)
            model = serializer.Meta.model
            unique_field = "reference" if model is Product else "code" if model in {ProductCategory, Warehouse, Unit} else None
            if unique_field and unique_field in serializer.validated_data:
                duplicate = model.objects.filter(company=self.request.user.company, **{unique_field: serializer.validated_data[unique_field]})
                if serializer.instance:
                    duplicate = duplicate.exclude(pk=serializer.instance.pk)
                if duplicate.exists():
                    raise exceptions.ValidationError("invalid_input")
            if isinstance(serializer, ProductSerializer):
                serializer.validate_catalog_relations(serializer.validated_data)
            created = serializer.instance is None
            obj = serializer.save(company=self.request.user.company)
            AuditEvent.objects.create(company=self.request.user.company, actor=self.request.user, actor_name=self.request.user.username, action="reference.created" if created else "reference.updated", object_type=type(obj).__name__.lower(), object_id=str(obj.pk), metadata={"fields": sorted(serializer.validated_data)})

    perform_create = _save
    perform_update = _save


class CustomerViewSet(ReferenceViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    search_fields = ["name", "email", "tax_id", "reference", "legal_name", "latin_name", "contact_name", "phone", "mobile", "city", "group_name"]
    ordering_fields = ["id", "name", "reference", "city", "archived"]

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in ("group_name", "city", "region"):
            value = self.request.query_params.get(field)
            if value is not None:
                if len(value) > 100:
                    raise exceptions.ValidationError("invalid_input")
                queryset = queryset.filter(**{field + "__icontains": value})
        return queryset

    def _save(self, serializer):
        with transaction.atomic():
            Company.objects.select_for_update().get(pk=self.request.user.company_id)
            reference = serializer.validated_data.get("reference")
            if reference:
                duplicate = Customer.objects.filter(company=self.request.user.company, reference=reference)
                if serializer.instance:
                    duplicate = duplicate.exclude(pk=serializer.instance.pk)
                if duplicate.exists():
                    raise exceptions.ValidationError("invalid_input")
            super()._save(serializer)

    perform_create = _save
    perform_update = _save

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        from .partner_api import customer_statement

        return customer_statement(request, self.get_object(), self)


class ProductViewSet(ReferenceViewSet):
    queryset = Product.objects.select_related("category", "unit").prefetch_related("warehouses")
    serializer_class = ProductSerializer
    search_fields = ["name", "reference", "specifications", "category__name", "category__code", "barcode", "latin_name", "manufacturer", "supplier_name"]
    ordering_fields = ["id", "name", "reference", "unit_price", "purchase_price", "archived"]

    @action(detail=True, methods=["get"])
    def pricing(self, request, pk=None):
        from .partner_api import product_pricing

        return product_pricing(request, self.get_object())

    def get_queryset(self):
        queryset = super().get_queryset()
        for field, model, lookup in (
            ("product", Product, "pk"), ("category", ProductCategory, "category_id"),
            ("unit", Unit, "unit_id"), ("warehouse", Warehouse, "warehouses__id"),
        ):
            value = self.request.query_params.get(field)
            if value is not None:
                if not value.isascii() or not value.isdecimal() or len(value) > 18:
                    raise exceptions.ValidationError("invalid_input")
                obj = get_object_or_404(model, company_id=self.request.user.company_id, pk=value)
                queryset = queryset.filter(**{lookup: obj.pk})
        specifications = self.request.query_params.get("specifications")
        if specifications is not None:
            if len(specifications) > 128:
                raise exceptions.ValidationError("invalid_input")
            queryset = queryset.filter(specifications__icontains=specifications)
        return queryset


class CatalogReferenceViewSet(ReferenceViewSet):
    search_fields = ["name", "code"]
    ordering_fields = ["id", "name", "code", "archived"]


class ProductCategoryViewSet(CatalogReferenceViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer


class WarehouseViewSet(CatalogReferenceViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer


class UnitViewSet(CatalogReferenceViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CompanyViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    action_roles = {"create": MANAGE_ROLES, "partial_update": MANAGE_ROLES, "validate": FINANCE_ROLES, "payments": FINANCE_ROLES, "duplicate": MANAGE_ROLES}
    search_fields = ["number", "customer__name", "snapshot__customer__name", "customer_reference", "document_title"]
    ordering_fields = ["id", "number", "issue_date", "due_date", "total", "status"]
    ordering = ["-issue_date", "-id"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("company", "customer")
        status = self.request.query_params.get("status")
        if status is not None:
            if status not in {"draft", "validated"}:
                raise exceptions.ValidationError("invalid_input")
            queryset = queryset.filter(status=status)
        queryset = self._related_filter(queryset, "customer", Customer)
        bounds = {}
        for parameter, lookup in (("date_from", "issue_date__gte"), ("date_to", "issue_date__lte")):
            value = self.request.query_params.get(parameter)
            if value is not None:
                try:
                    bounds[parameter] = date.fromisoformat(value)
                except (TypeError, ValueError):
                    raise exceptions.ValidationError("invalid_input") from None
                queryset = queryset.filter(**{lookup: bounds[parameter]})
        if bounds.get("date_from") and bounds.get("date_to") and bounds["date_from"] > bounds["date_to"]:
            raise exceptions.ValidationError("invalid_input")
        payment_status = self.request.query_params.get("payment_status")
        if payment_status is not None and payment_status not in {"unpaid", "overdue", "settled"}:
            raise exceptions.ValidationError("invalid_input")
        if payment_status or self.action == "list":
            queryset = queryset.annotate(paid_amount=Coalesce(Sum("payments__amount"), Value(Decimal("0")), output_field=DecimalField(max_digits=22, decimal_places=6)))
        if payment_status:
            queryset = queryset.filter(status="validated")
            queryset = queryset.filter(total=F("paid_amount")) if payment_status == "settled" else queryset.filter(total__gt=F("paid_amount"))
            if payment_status == "overdue":
                queryset = queryset.filter(due_date__lt=timezone.localdate())
        if self.action == "list":
            return queryset.defer("snapshot").annotate(
                frozen_customer_name=KeyTextTransform("name", KeyTransform("customer", "snapshot")),
            )
        return queryset.prefetch_related("lines", "payments")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "detail": self.action != "list"}

    def _response(self, invoice, status=200):
        obj = Invoice.objects.filter(company_id=self.request.user.company_id).select_related("company", "customer").prefetch_related("lines", "payments").get(pk=invoice.pk)
        return Response(InvoiceSerializer(obj, context={"detail": True}).data, status=status)

    def create(self, request):
        serializer = DraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._response(save_draft(request.user.company, request.user, serializer.validated_data), status=201)

    def partial_update(self, request, pk=None):
        obj = self.get_object()
        serializer = DraftSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return self._response(save_draft(request.user.company, request.user, serializer.validated_data, invoice_id=obj.pk))

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        obj = self.get_object()
        if request.data != {}:
            raise exceptions.ValidationError("invalid_input")
        return self._response(validate_invoice(request.user.company, request.user, obj.pk, request.headers.get("Idempotency-Key"), payload={}))

    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        obj = self.get_object()
        serializer = PaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._response(record_payment(request.user.company, request.user, obj.pk, request.headers.get("Idempotency-Key"), serializer.validated_data))

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        obj = self.get_object()
        response = Response(preview_invoice(request.user.company, request.user, obj.pk))
        response["Cache-Control"] = "no-store"
        return response

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        obj = self.get_object()
        serializer = DuplicateInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._response(duplicate_invoice(request.user.company, request.user, obj.pk, request.headers.get("Idempotency-Key"), serializer.validated_data), status=201)


class ReadOnlyCompanyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CompanyViewSet):
    http_method_names = ["get", "head", "options"]


class AccountViewSet(ReadOnlyCompanyViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    search_fields = ["code", "name"]
    ordering_fields = ["code", "id", "name"]
    ordering = ["code"]


class JournalViewSet(ReadOnlyCompanyViewSet):
    queryset = Journal.objects.all()
    serializer_class = JournalSerializer
    search_fields = ["code", "name"]
    ordering_fields = ["code", "id", "name"]
    ordering = ["code"]


class PeriodViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CompanyViewSet):
    queryset = Period.objects.all()
    serializer_class = PeriodSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    action_roles = {"create": ADMIN_ROLES, "partial_update": ADMIN_ROLES}
    search_fields = ["name"]
    ordering_fields = ["start", "end", "name", "id"]
    ordering = ["-start"]

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(set_period(request.user.company, request.user, serializer.validated_data)).data, status=201)

    def partial_update(self, request, pk=None):
        obj = self.get_object()
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(set_period(request.user.company, request.user, serializer.validated_data, period_id=obj.pk)).data)


class EntryViewSet(ReadOnlyCompanyViewSet):
    queryset = Entry.objects.select_related("journal", "company").prefetch_related("lines__account")
    serializer_class = EntrySerializer
    search_fields = ["reference"]
    ordering_fields = ["date", "id"]
    ordering = ["-date", "-id"]

    def get_queryset(self):
        queryset = self._related_filter(super().get_queryset(), "period", Period)
        return self._related_filter(queryset, "journal", Journal)


class TrialBalanceView(APIView):
    permission_classes = [IsAuthenticated, CompanyPermission]

    def get(self, request):
        period_id = request.query_params.get("period", "")
        if not period_id.isdecimal() or len(period_id) > 18:
            raise exceptions.ValidationError("invalid_input")
        period = get_object_or_404(Period, pk=period_id, company=request.user.company)
        movements = EntryLine.objects.filter(company=request.user.company, entry__company=request.user.company, entry__period=period).values("account_id").annotate(debit=Sum("debit"), credit=Sum("credit"))
        by_account = {row["account_id"]: row for row in movements}
        total_debit = total_credit = Decimal("0")
        accounts = []
        for account in Account.objects.filter(company=request.user.company).order_by("code"):
            row = by_account.get(account.pk, {})
            debit, credit = row.get("debit", Decimal("0")), row.get("credit", Decimal("0"))
            total_debit += debit
            total_credit += credit
            accounts.append({"code": account.code, "name": account.name, "debit": money(debit, request.user.company.precision), "credit": money(credit, request.user.company.precision), "balance": money(debit - credit, request.user.company.precision)})
        return Response({"accounts": accounts, "total_debit": money(total_debit, request.user.company.precision), "total_credit": money(total_credit, request.user.company.precision)})


class AuditViewSet(ReadOnlyCompanyViewSet):
    queryset = AuditEvent.objects.select_related("actor")
    serializer_class = AuditSerializer
    allowed_roles = FINANCE_ROLES
    search_fields = ["action", "object_type", "object_id"]
    ordering_fields = ["id", "created_at"]
    ordering = ["-created_at", "-id"]


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, CompanyViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    allowed_roles = ADMIN_ROLES
    search_fields = ["username"]
    ordering_fields = ["id", "username", "role", "is_active"]

    def _save(self, serializer):
        with transaction.atomic():
            Company.objects.select_for_update().get(pk=self.request.user.company_id)
            data = dict(serializer.validated_data)
            password = data.pop("password", None)
            if serializer.instance:
                user = User.objects.select_for_update().get(pk=serializer.instance.pk, company=self.request.user.company)
                if user.role == "admin" and user.is_active and (data.get("role", user.role) != "admin" or not data.get("is_active", user.is_active)):
                    if not User.objects.filter(company=user.company, role="admin", is_active=True).exclude(pk=user.pk).exists():
                        raise exceptions.ValidationError("invalid_input")
                before = {"role": user.role, "is_active": user.is_active}
                for key, value in data.items():
                    setattr(user, key, value)
                action_name = "user.updated"
            else:
                user = User(company=self.request.user.company, **data)
                before = None
                action_name = "user.created"
            if password is not None:
                user.set_password(password)
            user.save()
            serializer.instance = user
            AuditEvent.objects.create(company=user.company, actor=self.request.user, actor_name=self.request.user.username, action=action_name, object_type="user", object_id=str(user.pk), metadata={"before": before, "after": {"role": user.role, "is_active": user.is_active}, "password_changed": password is not None})

    perform_create = _save
    perform_update = _save

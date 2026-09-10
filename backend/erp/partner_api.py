"""Tarifs clients et relevés limités à la société de la session."""

from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, mixins, serializers
from rest_framework.response import Response

from .api import CompanyViewSet, StandardPagination
from .models import AuditEvent, Company, Customer, CustomerPrice, Invoice, Product
from .permissions import MANAGE_ROLES
from .serializers import CustomerSerializer, ExactDecimalField, StrictInputMixin, money


class CustomerPriceSerializer(StrictInputMixin, serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.none())
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none())
    unit_price = ExactDecimalField(max_digits=22, decimal_places=6, min_value=Decimal("0"))
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_reference = serializers.CharField(source="product.reference", read_only=True)

    class Meta:
        model = CustomerPrice
        fields = ("id", "customer", "customer_name", "product", "product_name", "product_reference", "unit_price", "archived")
        read_only_fields = ("id",)
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = self.context["request"].user.company
        self.fields["customer"].queryset = Customer.objects.filter(company=company)
        self.fields["product"].queryset = Product.objects.filter(company=company)


class CustomerPriceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, CompanyViewSet):
    queryset = CustomerPrice.objects.select_related("customer", "product")
    serializer_class = CustomerPriceSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    action_roles = {"create": MANAGE_ROLES, "partial_update": MANAGE_ROLES}
    search_fields = ["product__name", "product__reference", "customer__name"]
    ordering_fields = ["id", "unit_price"]

    def get_queryset(self):
        queryset = super().get_queryset().filter(customer__company=self.request.user.company, product__company=self.request.user.company)
        queryset = self._related_filter(queryset, "customer", Customer)
        queryset = self._related_filter(queryset, "product", Product)
        archived = self.request.query_params.get("archived")
        if archived is not None:
            if archived not in {"true", "false"}:
                raise exceptions.ValidationError("invalid_input")
            queryset = queryset.filter(archived=archived == "true")
        return queryset

    def _save(self, serializer):
        company = self.request.user.company
        with transaction.atomic():
            Company.objects.select_for_update().get(pk=company.pk)
            if serializer.instance:
                serializer.instance = CustomerPrice.objects.select_for_update().get(pk=serializer.instance.pk, company=company)
            customer = serializer.validated_data.get("customer", getattr(serializer.instance, "customer", None))
            product = serializer.validated_data.get("product", getattr(serializer.instance, "product", None))
            customer = get_object_or_404(Customer, pk=customer.pk, company=company)
            product = get_object_or_404(Product, pk=product.pk, company=company)
            # Une archive reste modifiable pour désactiver son tarif ; aucune nouvelle
            # association active ne peut cibler une référence déjà archivée.
            if not serializer.validated_data.get("archived", getattr(serializer.instance, "archived", False)) and (customer.archived or product.archived):
                raise exceptions.ValidationError("archived_reference")
            duplicate = CustomerPrice.objects.filter(company=company, customer=customer, product=product)
            if serializer.instance:
                duplicate = duplicate.exclude(pk=serializer.instance.pk)
            if duplicate.exists():
                raise exceptions.ValidationError("invalid_input")
            created = serializer.instance is None
            obj = serializer.save(company=company)
            AuditEvent.objects.create(company=company, actor=self.request.user, actor_name=self.request.user.username, action="reference.created" if created else "reference.updated", object_type="customerprice", object_id=str(obj.pk), metadata={"fields": sorted(serializer.validated_data)})

    perform_create = _save
    perform_update = _save


class StatementFilter(StrictInputMixin, serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, data):
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise serializers.ValidationError("invalid_input")
        return data


def customer_statement(request, customer, view):
    dates = StatementFilter(data={key: request.query_params[key] for key in ("start", "end") if key in request.query_params})
    dates.is_valid(raise_exception=True)
    invoices = Invoice.objects.filter(company=request.user.company, customer=customer, status="validated").annotate(
        paid_amount=Coalesce(Sum("payments__amount", filter=Q(payments__company=request.user.company)), Value(Decimal("0")), output_field=DecimalField(max_digits=22, decimal_places=6)),
    )
    for key, lookup in (("start", "issue_date__gte"), ("end", "issue_date__lte")):
        if key in dates.validated_data:
            invoices = invoices.filter(**{lookup: dates.validated_data[key]})
    totals = invoices.aggregate(total=Sum("total"), paid=Sum("paid_amount"))
    total, paid = totals["total"] or Decimal("0"), totals["paid"] or Decimal("0")
    overdue = invoices.filter(due_date__lt=timezone.localdate()).aggregate(value=Sum(F("total") - F("paid_amount")))["value"] or Decimal("0")
    precision = request.user.company.precision
    paginator = StandardPagination()
    page = paginator.paginate_queryset(invoices.order_by("issue_date", "id").prefetch_related("payments"), request, view=view)
    rows = [{"id": invoice.pk, "number": invoice.number, "issue_date": invoice.issue_date, "due_date": invoice.due_date,
             "total": money(invoice.total, invoice.precision), "paid": money(invoice.paid_amount, invoice.precision), "balance": money(invoice.total - invoice.paid_amount, invoice.precision),
             "payments": [{"id": payment.pk, "date": payment.date, "reference": payment.reference, "amount": money(payment.amount, invoice.precision)} for payment in invoice.payments.all() if payment.company_id == customer.company_id]}
            for invoice in page]
    response = paginator.get_paginated_response(rows)
    response.data.update({"customer": CustomerSerializer(customer).data, "currency": request.user.company.currency,
                          "summary": {"invoice_count": paginator.page.paginator.count, "total": money(total, precision), "paid": money(paid, precision), "balance": money(total - paid, precision), "overdue": money(overdue, precision)}})
    return response


def product_pricing(request, product):
    value = request.query_params.get("customer", "")
    if not value.isascii() or not value.isdecimal() or len(value) > 18:
        raise exceptions.ValidationError("invalid_input")
    customer = get_object_or_404(Customer, pk=value, company=request.user.company)
    if customer.archived or product.archived:
        raise exceptions.ValidationError("archived_reference")
    price = CustomerPrice.objects.filter(company=request.user.company, customer=customer, product=product, archived=False).first()
    return Response({"product": product.pk, "customer": customer.pk, "unit_price": format(price.unit_price if price else product.unit_price, "f"), "tax_rate": format(product.tax_rate, "f"), "discount_rate": format(customer.default_discount_rate, "f"), "source": "customer" if price else "catalog"})

"""Tableau de bord et exports bornés, exclusivement dans la société du compte."""
import csv
import io
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, CharField, DecimalField, F, Q, Sum, TextField, Value, When
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, Customer, Invoice, Payment, Product
from .permissions import CompanyPermission
from .serializers import money


def date_bounds(request):
    result = {}
    for key in ("start", "end"):
        value = request.query_params.get(key, "")
        if value:
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError
                result[key] = parsed
            except (ValueError, TypeError):
                raise exceptions.ValidationError("invalid_input") from None
    if result.get("start", date.min) > result.get("end", date.max):
        raise exceptions.ValidationError("invalid_input")
    return result


def bounded_dates(queryset, field, bounds):
    if "start" in bounds:
        queryset = queryset.filter(**{field + "__gte": bounds["start"]})
    if "end" in bounds:
        queryset = queryset.filter(**{field + "__lte": bounds["end"]})
    return queryset


def with_balance(queryset):
    return queryset.annotate(
        paid_amount=Coalesce(Sum("payments__amount"), Value(Decimal("0")),
                             output_field=DecimalField(max_digits=22, decimal_places=6)),
    ).annotate(open_amount=F("total") - F("paid_amount"))


class DashboardView(APIView):
    permission_classes = [IsAuthenticated, CompanyPermission]

    @transaction.atomic
    def get(self, request):
        company = Company.objects.select_for_update().get(pk=request.user.company_id)
        bounds = date_bounds(request)
        invoices = Invoice.objects.filter(company=company)
        period = bounded_dates(invoices, "issue_date", bounds)
        validated = period.filter(status="validated")
        receipts = bounded_dates(Payment.objects.filter(company=company), "date", bounds)
        # Les soldes ouverts concernent toutes les factures validées, quel que soit le filtre de période.
        unpaid = with_balance(invoices.filter(status="validated")).filter(open_amount__gt=0)
        overdue = unpaid.filter(due_date__lt=timezone.localdate())
        def total(queryset, field):
            return queryset.aggregate(value=Sum(field))["value"] or Decimal("0")
        values = {
            "invoiced": total(validated, "total"), "received": total(receipts, "amount"),
            "outstanding": total(unpaid, "open_amount"), "overdue": total(overdue, "open_amount"),
        }
        rows = []
        for invoice in overdue.select_related("customer").order_by("due_date", "id")[:8]:
            rows.append({"id": invoice.pk, "number": invoice.number,
                         "customer_name": invoice.snapshot.get("customer", {}).get("name", invoice.customer.name),
                         "due_date": invoice.due_date.isoformat(),
                         "balance": money(invoice.open_amount, invoice.precision)})
        return Response({
            "currency": company.currency, "precision": company.precision,
            "metrics": {key: money(value, company.precision) for key, value in values.items()},
            "counts": {"drafts": period.filter(status="draft").count(), "validated": validated.count(),
                       "customers": Customer.objects.filter(company=company, archived=False).count(),
                       "products": Product.objects.filter(company=company, archived=False).count()},
            "overdue_invoices": rows,
            "period": {key: value.isoformat() for key, value in bounds.items()},
        })


def csv_cell(value):
    """Neutralise les formules à l'ouverture dans un tableur, sans conversion flottante."""
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


class ExportContentNegotiation(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        # Le succès est une HttpResponse CSV ; les erreurs restent du JSON API.
        if request.headers.get("Accept", "").split(";")[0] == "text/csv":
            return renderers[0], renderers[0].media_type
        return super().select_renderer(request, renderers, format_suffix)


class ExportView(APIView):
    permission_classes = [IsAuthenticated, CompanyPermission]
    content_negotiation_class = ExportContentNegotiation
    limit = 5000

    def get(self, request):
        company = request.user.company
        resource = request.query_params.get("resource", "")
        bounds = date_bounds(request)
        search = request.query_params.get("search", "")
        if len(search) > 128:
            raise exceptions.ValidationError("invalid_input")
        if resource == "customers":
            queryset = Customer.objects.filter(company=company).filter(Q(name__icontains=search) | Q(email__icontains=search))
            fields = ["id", "reference", "name", "legal_name", "contact_name", "email", "phone", "mobile", "address", "postal_code", "city", "region", "country", "tax_id", "group_name", "payment_terms_days", "default_discount_rate", "archived"]
        elif resource == "products":
            queryset = Product.objects.filter(company=company).filter(Q(name__icontains=search) | Q(reference__icontains=search))
            fields = ["id", "reference", "name", "barcode", "manufacturer", "supplier_name", "unit_price", "purchase_price", "tax_rate", "category__name", "unit__name", "weight", "specifications", "archived"]
        elif resource == "invoices":
            queryset = bounded_dates(Invoice.objects.filter(company=company), "issue_date", bounds)
            queryset = queryset.annotate(customer_label=Coalesce(KeyTextTransform("name", KeyTransform("customer", "snapshot")), F("customer__name"), output_field=TextField()))
            queryset = queryset.annotate(effective_currency=Case(When(status="draft", then=Value(company.currency)), default=F("currency"), output_field=CharField()))
            queryset = queryset.filter(Q(number__icontains=search) | Q(customer_label__icontains=search))
            fields = ["id", "number", "customer_label", "customer_reference", "issue_date", "due_date", "status", "effective_currency", "net", "tax", "total"]
        elif resource == "payments":
            if request.user.role not in {"admin", "accountant"}:
                raise exceptions.PermissionDenied()
            queryset = bounded_dates(Payment.objects.filter(company=company), "date", bounds)
            queryset = queryset.filter(Q(reference__icontains=search) | Q(invoice__number__icontains=search))
            fields = ["id", "invoice__number", "date", "reference", "amount"]
        else:
            raise exceptions.ValidationError("invalid_input")
        archived = request.query_params.get("archived", "")
        if archived:
            if archived not in {"true", "false"} or resource not in {"customers", "products"}:
                raise exceptions.ValidationError("invalid_input")
            queryset = queryset.filter(archived=archived == "true")
        status = request.query_params.get("status", "")
        if status:
            if resource != "invoices" or status not in {"draft", "validated"}:
                raise exceptions.ValidationError("invalid_input")
            queryset = queryset.filter(status=status)
        rows = list(queryset.order_by("id").values_list(*fields)[:self.limit + 1])
        if len(rows) > self.limit:
            return Response({"code": "export_limit", "detail": "export_limit"}, status=400)
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow(csv_cell(value) for value in row)
        response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="azula-{resource}.csv"'
        response["Cache-Control"] = "no-store, private"
        return response

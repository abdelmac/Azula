from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator, URLValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

LANGUAGES = [(value, value) for value in ("fr", "en", "ar", "de", "tr")]
MONEY = {"max_digits": 22, "decimal_places": 6}


class Company(models.Model):
    print_settings = models.JSONField(default=dict, blank=True)
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    precision = models.PositiveSmallIntegerField(
        default=2, validators=[MinValueValidator(0), MaxValueValidator(4)]
    )
    document_language = models.CharField(max_length=2, choices=LANGUAGES, default="fr")
    locale = models.CharField(
        max_length=20,
        default="fr-FR",
        validators=[RegexValidator(r"^[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?$", message="Paramètres régionaux invalides.")],
    )

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(precision__lte=4), name="company_precision_range")]


class User(AbstractUser):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    role = models.CharField(max_length=20, choices=[(v, v) for v in ("admin", "accountant", "sales", "viewer")], default="viewer")
    language = models.CharField(max_length=2, choices=LANGUAGES, default="fr")


class CompanyOwned(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class Customer(CompanyOwned):
    name = models.CharField(max_length=200)
    reference = models.CharField(max_length=80, blank=True)
    legal_name = models.CharField(max_length=200, blank=True)
    latin_name = models.CharField(max_length=200, blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    phone_alt = models.CharField(max_length=40, blank=True)
    mobile = models.CharField(max_length=40, blank=True)
    fax = models.CharField(max_length=40, blank=True)
    website = models.URLField(max_length=500, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, blank=True)
    shipping_address = models.TextField(max_length=2000, blank=True)
    group_name = models.CharField(max_length=100, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(365)])
    default_discount_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0"))
    credit_limit = models.DecimalField(**MONEY, null=True, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    bic = models.CharField(max_length=11, blank=True)
    notes = models.TextField(max_length=4000, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    tax_id = models.CharField(max_length=80, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["company", "archived", "name"])]
        constraints = [
            models.UniqueConstraint(fields=["company", "reference"], condition=~Q(reference=""), name="customer_company_reference"),
            models.CheckConstraint(condition=Q(payment_terms_days__lte=365), name="customer_payment_days"),
            models.CheckConstraint(condition=Q(default_discount_rate__gte=0, default_discount_rate__lte=100), name="customer_discount_range"),
            models.CheckConstraint(condition=Q(credit_limit__isnull=True) | Q(credit_limit__gte=0), name="customer_credit_nonnegative"),
        ]


class CatalogReference(CompanyOwned):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    archived = models.BooleanField(default=False)

    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="%(class)s_company_code")]
        indexes = [models.Index(fields=["company", "archived", "name"])]


class ProductCategory(CatalogReference):
    pass


class Warehouse(CatalogReference):
    pass


class Unit(CatalogReference):
    pass


class Product(CompanyOwned):
    reference = models.CharField(max_length=80)
    name = models.CharField(max_length=200)
    latin_name = models.CharField(max_length=200, blank=True)
    barcode = models.CharField(max_length=80, blank=True)
    manufacturer = models.CharField(max_length=150, blank=True)
    supplier_name = models.CharField(max_length=150, blank=True)
    color = models.CharField(max_length=80, blank=True)
    dimensions = models.CharField(max_length=150, blank=True)
    origin = models.CharField(max_length=100, blank=True)
    weight = models.DecimalField(max_digits=16, decimal_places=6, null=True, blank=True)
    notes = models.TextField(max_length=4000, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    unit_price = models.DecimalField(**MONEY)
    purchase_price = models.DecimalField(**MONEY, null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0"))
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    warehouses = models.ManyToManyField(Warehouse, blank=True, related_name="products")
    specifications = models.TextField(max_length=4000, blank=True)
    image_url = models.URLField(max_length=1000, blank=True, validators=[URLValidator(schemes=["https"])])
    archived = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "reference"], name="product_company_reference"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="product_nonnegative_price"),
            models.CheckConstraint(condition=Q(purchase_price__isnull=True) | Q(purchase_price__gte=0), name="product_nonnegative_purchase"),
            models.CheckConstraint(condition=Q(tax_rate__gte=0, tax_rate__lte=100), name="product_tax_range"),
            models.CheckConstraint(condition=Q(weight__isnull=True) | Q(weight__gte=0), name="product_weight_nonnegative"),
        ]
        indexes = [models.Index(fields=["company", "archived", "name"])]


class CustomerPrice(CompanyOwned):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="prices")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="customer_prices")
    unit_price = models.DecimalField(**MONEY)
    archived = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "customer", "product"], name="customer_price_unique"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="customer_price_nonnegative"),
        ]


class Invoice(CompanyOwned):
    customer_reference = models.CharField(max_length=200, blank=True)
    document_title = models.CharField(max_length=150, blank=True)
    notes = models.TextField(max_length=4000, blank=True)
    payment_terms = models.TextField(max_length=2000, blank=True)
    shipping_address = models.TextField(max_length=2000, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    issue_date = models.DateField()
    due_date = models.DateField()
    document_language = models.CharField(max_length=2, choices=LANGUAGES, default="fr")
    status = models.CharField(max_length=12, choices=[("draft", "draft"), ("validated", "validated")], default="draft")
    number = models.CharField(max_length=40, blank=True, default="")
    precision = models.PositiveSmallIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True, default="")
    net = models.DecimalField(**MONEY, default=Decimal("0"))
    tax = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "number"], condition=~Q(number=""), name="invoice_unique_number"),
            models.CheckConstraint(condition=Q(net__gte=0, tax__gte=0, total__gte=0), name="invoice_nonnegative_amounts"),
            models.CheckConstraint(condition=Q(due_date__gte=models.F("issue_date")), name="invoice_dates_order"),
            models.CheckConstraint(condition=Q(total=models.F("net") + models.F("tax")), name="invoice_total_sum"),
            models.CheckConstraint(condition=Q(status="draft") | (Q(status="validated", precision__isnull=False, validated_at__isnull=False) & ~Q(number="") & ~Q(currency="")), name="invoice_validation_state"),
        ]
        indexes = [models.Index(fields=["company", "status", "-issue_date", "-id"]), models.Index(fields=["company", "-issue_date", "-id"]), models.Index(fields=["company", "customer"])]

    @property
    def paid(self):
        if "paid_amount" in self.__dict__:
            return self.paid_amount
        if "_paid_amount" in self.__dict__:
            return self._paid_amount
        if "payments" in getattr(self, "_prefetched_objects_cache", {}):
            return sum((payment.amount for payment in self.payments.all()), Decimal("0"))
        return self.payments.aggregate(amount=Sum("amount"))["amount"] or Decimal("0")

    @property
    def balance(self):
        return self.total - self.paid

    def save(self, *args, **kwargs):
        if self.pk and Invoice.objects.filter(pk=self.pk, status="validated").exists():
            raise ValidationError("immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == "validated":
            raise ValidationError("immutable")
        return super().delete(*args, **kwargs)


class InvoiceLine(CompanyOwned):
    discount_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0"))
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField(default=0)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=16, decimal_places=6)
    unit_price = models.DecimalField(**MONEY)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4)
    net = models.DecimalField(**MONEY)
    tax = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0, unit_price__gte=0, net__gte=0, tax__gte=0), name="invoice_line_amounts"),
            models.CheckConstraint(condition=Q(tax_rate__gte=0, tax_rate__lte=100), name="invoice_line_tax_range"),
            models.CheckConstraint(condition=Q(discount_rate__gte=0, discount_rate__lte=100), name="invoice_line_discount_range"),
            models.CheckConstraint(condition=Q(total=models.F("net") + models.F("tax")), name="invoice_line_total_sum"),
        ]


class Period(CompanyOwned):
    name = models.CharField(max_length=100)
    start = models.DateField()
    end = models.DateField()
    closed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gte=models.F("start")), name="period_dates_order")]
        indexes = [models.Index(fields=["company", "start", "end"])]


class Account(CompanyOwned):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=20, choices=[(v, v) for v in ("receivable", "revenue", "tax", "bank")])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="account_company_code"), models.UniqueConstraint(fields=["company", "kind"], name="account_company_kind")]
        ordering = ["code"]


class Journal(CompanyOwned):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="journal_company_code")]


class ImmutableRecord(CompanyOwned):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("immutable")


class Payment(ImmutableRecord):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(**MONEY)
    date = models.DateField()
    reference = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="payment_positive_amount")]
        ordering = ["date", "id"]


class Entry(ImmutableRecord):
    transaction_id = models.BigIntegerField(editable=False, null=True)
    date = models.DateField()
    reference = models.CharField(max_length=200)
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT)
    period = models.ForeignKey(Period, on_delete=models.PROTECT)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="entries")
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="entry")
    kind = models.CharField(max_length=20, choices=[("invoice", "invoice"), ("payment", "payment")])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["invoice"], condition=Q(kind="invoice"), name="single_invoice_entry")]
        indexes = [models.Index(fields=["company", "period", "date"]), models.Index(fields=["company", "journal", "date"])]

    @property
    def total_debit(self):
        return sum((line.debit for line in self.lines.all()), Decimal("0"))

    @property
    def total_credit(self):
        return sum((line.credit for line in self.lines.all()), Decimal("0"))


class EntryLine(ImmutableRecord):
    entry = models.ForeignKey(Entry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(**MONEY, default=Decimal("0"))
    credit = models.DecimalField(**MONEY, default=Decimal("0"))

    class Meta:
        constraints = [models.CheckConstraint(condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)), name="entry_line_one_positive_side")]


class AuditEvent(ImmutableRecord):
    actor = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    actor_name = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["company", "-created_at"])]


class IdempotencyRecord(CompanyOwned):
    key = models.CharField(max_length=128)
    action = models.CharField(max_length=30)
    fingerprint = models.CharField(max_length=64)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "key"], name="idempotency_company_key")]


class NumberSequence(CompanyOwned):
    year = models.PositiveIntegerField()
    next_value = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "year"], name="sequence_company_year")]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_started = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)

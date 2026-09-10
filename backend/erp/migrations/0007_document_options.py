from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("erp", "0006_partner_details")]
    operations = [
        migrations.AddField(model_name="company", name="print_settings", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="invoice", name="customer_reference", field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name="invoice", name="document_title", field=models.CharField(blank=True, max_length=150)),
        migrations.AddField(model_name="invoice", name="notes", field=models.TextField(blank=True, max_length=4000)),
        migrations.AddField(model_name="invoice", name="payment_terms", field=models.TextField(blank=True, max_length=2000)),
        migrations.AddField(model_name="invoice", name="shipping_address", field=models.TextField(blank=True, max_length=2000)),
        migrations.AddField(model_name="invoiceline", name="discount_rate", field=models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=7)),
        migrations.AddConstraint(model_name="invoiceline", constraint=models.CheckConstraint(condition=models.Q(discount_rate__gte=0, discount_rate__lte=100), name="invoice_line_discount_range")),
    ]

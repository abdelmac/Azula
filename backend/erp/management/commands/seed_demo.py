from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from erp.management.synthetic import synthetic_arguments, synthetic_company
from erp.models import Company, Customer, IdempotencyRecord, Period, Product
from erp.services import DomainError, bootstrap_company, record_payment, save_draft, set_period, validate_invoice


class Command(BaseCommand):
    help = "Ajoute une facture synthétique 100 + 20 de taxe, validée et réglée à hauteur de 50."

    def add_arguments(self, parser):
        synthetic_arguments(parser)

    @transaction.atomic
    def handle(self, *args, **options):
        company, actor = synthetic_company(options)
        Company.objects.select_for_update().get(pk=company.pk)
        if company.precision != 2:
            raise CommandError("Le scénario 100,00 + 20,00 exige une précision de démonstration de 2.")
        previous = IdempotencyRecord.objects.filter(company=company, key="demo-v1-validation").first()
        if previous:
            self.stdout.write(f"Scénario déjà présent : facture {previous.invoice_id}.")
            return
        today = date.today()
        bootstrap_company(company)
        period = Period.objects.filter(company=company, start__lte=today, end__gte=today).first()
        if period and period.closed:
            raise CommandError("La période actuelle est fermée ; aucune donnée de démonstration ajoutée.")
        try:
            if period is None:
                set_period(company, actor, {"name": f"Démonstration {today.year}", "start": date(today.year, 1, 1), "end": date(today.year, 12, 31), "closed": False})
            customer, _ = Customer.objects.get_or_create(company=company, tax_id="AZULA-DEMO-V1", defaults={"name": "Atelier Démonstration / ورشة تجريبية", "email": "demo@example.invalid", "address": "Adresse fictive — données synthétiques"})
            product, _ = Product.objects.get_or_create(company=company, reference="DEMO-SERVICE-V1", defaults={"name": "Prestation de démonstration", "unit_price": "100.00", "tax_rate": "20.0000"})
            invoice = save_draft(company, actor, {"customer": customer.pk, "issue_date": today, "due_date": today, "document_language": company.document_language, "lines": [{"product": product.pk, "description": "Prestation de démonstration — taxe de test", "quantity": "1", "unit_price": "100.00", "tax_rate": "20"}]})
            invoice = validate_invoice(company, actor, invoice.pk, "demo-v1-validation")
            record_payment(company, actor, invoice.pk, "demo-v1-payment-50", {"amount": "50.00", "date": today, "reference": "Règlement fictif — aucun transfert bancaire"})
        except DomainError as error:
            raise CommandError(f"Scénario refusé : {error.code}.") from None
        self.stdout.write(self.style.SUCCESS(f"Facture {invoice.number} (id {invoice.pk}) : total 120,00, règlement fictif 50,00, solde 70,00 {company.currency}."))

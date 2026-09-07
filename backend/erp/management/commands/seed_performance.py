import re
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from erp.management.synthetic import synthetic_arguments, synthetic_company
from erp.models import AuditEvent, Company, Customer, Invoice, InvoiceLine


class Command(BaseCommand):
    help = "Crée par lots 100 000 factures brouillon et 10 000 clients synthétiques dans une base jetable."

    def add_arguments(self, parser):
        synthetic_arguments(parser)
        parser.add_argument("--invoices", type=int, default=100_000)
        parser.add_argument("--customers", type=int, default=10_000)
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--lines-per-invoice", type=int, default=1)
        parser.add_argument("--dataset", default="perf-v1", help="Identifiant du jeu ; une réutilisation est refusée sans supprimer de données.")

    def handle(self, *args, **options):
        company, actor = synthetic_company(options)
        if not 1 <= options["customers"] <= 100_000 or not 1 <= options["invoices"] <= 1_000_000 or not 1 <= options["batch_size"] <= 5000 or not 1 <= options["lines_per_invoice"] <= 10:
            raise CommandError("Volumes autorisés : clients 1..100000, factures 1..1000000, lot 1..5000, lignes 1..10.")
        if not re.fullmatch(r"[a-zA-Z0-9-]{1,30}", options["dataset"]):
            raise CommandError("Identifiant de jeu invalide (lettres, chiffres et tirets ; 30 caractères maximum).")
        marker = f"SYNTHETIC-{options['dataset']}-"
        with transaction.atomic():
            Company.objects.select_for_update().get(pk=company.pk)
            if Customer.objects.filter(company=company, tax_id__startswith=marker).exists() or AuditEvent.objects.filter(company=company, action="synthetic.performance_started", metadata__dataset=options["dataset"]).exists():
                raise CommandError("Ce jeu existe déjà, éventuellement partiellement. Utilisez une nouvelle base jetable ou un autre --dataset ; aucune suppression automatique.")
            # Ce marqueur réservé rend explicite un éventuel arrêt après un lot.
            AuditEvent.objects.create(company=company, actor=actor, actor_name=actor.username, action="synthetic.performance_started", object_type="company", object_id=str(company.pk), metadata={"dataset": options["dataset"]})
        batch_size = options["batch_size"]
        customer_ids = []
        for offset in range(0, options["customers"], batch_size):
            rows = [Customer(company=company, name=f"Client synthétique {options['dataset']} {index:06d}", tax_id=marker + str(index), email=f"client-{index}@example.invalid") for index in range(offset, min(offset + batch_size, options["customers"]))]
            Customer.objects.bulk_create(rows, batch_size=batch_size)
            customer_ids.extend(row.pk for row in rows)
        today = date.today()
        line_count = options["lines_per_invoice"]
        # Entrées fixes en Decimal, mêmes résultats HALF_UP que le service.
        net, tax = Decimal("100") * line_count, Decimal("20") * line_count
        for offset in range(0, options["invoices"], batch_size):
            with transaction.atomic():
                rows = [Invoice(company=company, customer_id=customer_ids[index % len(customer_ids)], issue_date=today - timedelta(days=index % 365), due_date=today + timedelta(days=30), document_language=company.document_language, net=net, tax=tax, total=net + tax) for index in range(offset, min(offset + batch_size, options["invoices"]))]
                Invoice.objects.bulk_create(rows, batch_size=batch_size)
                InvoiceLine.objects.bulk_create([InvoiceLine(company=company, invoice=row, position=position, description=f"Prestation synthétique {options['dataset']}", quantity=Decimal("1"), unit_price=Decimal("100"), tax_rate=Decimal("20"), net=Decimal("100"), tax=Decimal("20"), total=Decimal("120")) for row in rows for position in range(line_count)], batch_size=batch_size)
            if offset % (batch_size * 10) == 0 or offset + batch_size >= options["invoices"]:
                self.stdout.write(f"{min(offset + batch_size, options['invoices'])}/{options['invoices']} factures créées.")
        AuditEvent.objects.create(company=company, actor=actor, actor_name=actor.username, action="synthetic.performance_created", object_type="company", object_id=str(company.pk), metadata={"dataset": options["dataset"], "invoices": options["invoices"], "customers": options["customers"], "lines_per_invoice": line_count})
        self.stdout.write(self.style.SUCCESS("Jeu synthétique prêt. Les factures sont des brouillons sans écritures ; aucun benchmark n'a été exécuté par cette commande."))

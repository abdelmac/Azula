from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from billing.models import Subscription
from erp.models import AuditEvent, Company


class Command(BaseCommand):
    help = "Définit explicitement une exemption ou l’obligation d’abonnement pour une société."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", required=True, type=int)
        parser.add_argument("--expected-name", required=True)
        parser.add_argument("--mode", choices=["exempt", "required"], required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **options):
        if not options["reason"].strip() or len(options["reason"]) > 500:
            raise CommandError("Une justification de 1 à 500 caractères est requise.")
        with transaction.atomic():
            company = Company.objects.select_for_update().filter(pk=options["company_id"]).first()
            if not company or company.name != options["expected_name"]:
                raise CommandError("La société ne correspond pas à la cible explicitement choisie.")
            subscription, _ = Subscription.objects.get_or_create(company=company, defaults={"livemode": settings.STRIPE_LIVE_MODE})
            subscription.exempt = options["mode"] == "exempt"
            subscription.save(update_fields=["exempt", "updated_at"])
            AuditEvent.objects.create(company=company, actor_name="Opérateur Azula", action="subscription.policy_changed",
                object_type="subscription", object_id=str(company.pk), metadata={"exempt": subscription.exempt, "reason": options["reason"]})
        self.stdout.write(self.style.SUCCESS("Politique enregistrée et auditée. Aucun paiement créé."))

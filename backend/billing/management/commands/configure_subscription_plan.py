"""Import explicite d'un tarif Stripe existant ; aucun produit/prix créé à distance."""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from billing import provider
from billing.exceptions import BillingError
from billing.models import Plan
from billing.services import call, identifier, validate_price


class Command(BaseCommand):
    help = "Importe un prix récurrent Stripe existant dans le catalogue des abonnements Azula."

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True)
        parser.add_argument("--price-id", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--description", default="")
        parser.add_argument("--trial-days", type=int, default=0)
        parser.add_argument("--inactive", action="store_true")

    def handle(self, *args, **options):
        if (not re.fullmatch(r"[-a-zA-Z0-9_]{1,60}", options["code"])
                or not 1 <= len(options["name"]) <= 120 or len(options["description"]) > 500
                or options["trial_days"] not in [0, *range(2, 91)]):
            raise CommandError("Code, nom, description ou durée d’essai invalide (0 ou 2 à 90 jours).")
        try:
            price = call(provider.retrieve_price, identifier(options["price_id"], "price_"))
            values = validate_price(price)
        except BillingError as error:
            raise CommandError(error.code) from None
        with transaction.atomic():
            existing = Plan.objects.select_for_update().filter(code=options["code"]).first()
            if existing and existing.stripe_price_id != options["price_id"]:
                raise CommandError("Utiliser un nouveau code pour un nouveau prix ; le tarif historique est conservé.")
            if Plan.objects.filter(stripe_price_id=options["price_id"]).exclude(code=options["code"]).exists():
                raise CommandError("Ce prix est déjà associé à un autre code.")
            Plan.objects.update_or_create(code=options["code"], defaults={
                **values, "stripe_price_id": options["price_id"], "name": options["name"],
                "description": options["description"], "trial_days": options["trial_days"], "active": not options["inactive"],
            })
        self.stdout.write(self.style.SUCCESS("Tarif importé. Aucun abonnement ni paiement créé."))

import getpass
import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from erp.models import AuditEvent, Company, User
from erp.services import bootstrap_company


class Command(BaseCommand):
    help = "Crée la première société et son administrateur ; mot de passe saisi sans affichage."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--company-name", required=True)
        parser.add_argument("--currency", required=True, help="Code de devise explicite, par exemple EUR ; aucun choix fiscal automatique.")
        parser.add_argument("--precision", type=int, choices=range(5), default=2)
        parser.add_argument("--language", choices=["fr", "en", "ar", "de", "tr"], default="fr")
        parser.add_argument("--locale", default="fr-FR")

    def handle(self, *args, **options):
        if Company.objects.exists() or User.objects.exists():
            raise CommandError("Installation déjà initialisée. Utilisez la gestion des utilisateurs avec un compte administrateur.")
        if not re.fullmatch(r"[A-Z]{3}", options["currency"]):
            raise CommandError("La devise doit être un code de trois lettres majuscules choisi explicitement.")
        company = Company(name=options["company_name"], currency=options["currency"], precision=options["precision"], document_language=options["language"], locale=options["locale"])
        user = User(username=options["username"], role="admin", language=options["language"], is_staff=True, is_superuser=False)
        try:
            company.full_clean()
            user.full_clean(exclude=["company", "password"])
            password = getpass.getpass("Mot de passe administrateur (12 caractères minimum) : ")
            confirmation = getpass.getpass("Confirmez le mot de passe : ")
            if password != confirmation:
                raise CommandError("Les mots de passe ne correspondent pas.")
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from None
        except (EOFError, KeyboardInterrupt):
            raise CommandError("Création annulée ; aucune donnée écrite.") from None
        with transaction.atomic():
            # La toute première société n'a pas encore de ligne à verrouiller.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [732041860125])
            if Company.objects.exists() or User.objects.exists():
                raise CommandError("L'installation vient d'être initialisée par une autre opération.")
            company.save()
            user.company = company
            user.set_password(password)
            user.save()
            bootstrap_company(company)
            AuditEvent.objects.create(company=company, actor=user, actor_name=user.username, action="installation.initialized", object_type="company", object_id=str(company.pk), metadata={"currency": company.currency, "precision": company.precision})
        self.stdout.write(self.style.SUCCESS(f"Société {company.pk} et administrateur créés. Le plan de comptes initial est démonstratif, sans conformité fiscale présumée."))

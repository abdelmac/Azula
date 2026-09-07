from django.conf import settings
from django.core.management.base import CommandError

from erp.models import Company, User


def synthetic_company(options):
    if settings.ENVIRONMENT == "production" or not settings.ALLOW_DEMO_DATA or not options["confirm_synthetic"]:
        raise CommandError("Données synthétiques interdites : exige ENVIRONMENT différent de production, ALLOW_DEMO_DATA=1 et --confirm-synthetic. Réservez cette commande à une base jetable.")
    try:
        company = Company.objects.get(pk=options["company"])
    except Company.DoesNotExist:
        raise CommandError("Société introuvable ; initialisez d'abord une installation jetable.") from None
    actor = User.objects.filter(company=company, role="admin", is_active=True).order_by("id").first()
    if actor is None:
        raise CommandError("Un administrateur actif de cette société est nécessaire.")
    return company, actor


def synthetic_arguments(parser):
    parser.add_argument("--company", required=True, type=int)
    parser.add_argument("--confirm-synthetic", action="store_true", help="Confirme que la base cible est jetable et ne contient aucune donnée réelle.")

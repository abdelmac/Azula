"""Préparer uniquement une base jetable nommée azula_e2e, jamais une installation normale."""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from erp.models import Company, User
from erp.services import bootstrap_company, set_period

if settings.ENVIRONMENT != "test" or settings.DATABASES["default"]["NAME"] != "azula_e2e":
    raise SystemExit("Refus : ENVIRONMENT=test et DB_NAME=azula_e2e obligatoires.")
password = os.environ.get("E2E_PASSWORD", "")
validate_password(password)
if Company.objects.exists() or User.objects.exists():
    raise SystemExit("Refus : base E2E déjà initialisée. Aucune donnée modifiée.")
with transaction.atomic():
    company = Company.objects.create(name="Azula E2E", currency="EUR", precision=2, locale="fr-FR")
    user = User.objects.create_user(username=os.environ.get("E2E_USERNAME", "e2e-admin"), password=password, company=company, role="admin")
    bootstrap_company(company)
    today = date.today()
    set_period(company, user, {"name": str(today.year), "start": date(today.year, 1, 1), "end": date(today.year, 12, 31), "closed": False})
print("Base E2E préparée. Identifiants fournis uniquement par environnement.")

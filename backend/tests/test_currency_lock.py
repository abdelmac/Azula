"""La monnaie ne peut pas réétiqueter les comptes ou transactions déjà reçus."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from connections.models import BankAccount, ExternalTransaction, Integration
from erp.models import Company, User
from erp.services import DomainError, configure_company

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def company_actor():
    company = Company.objects.create(name="Devise figée", currency="EUR", precision=2)
    actor = User.objects.create_user(username="currency-admin", company=company, role="admin")
    return company, actor


@pytest.mark.parametrize("record", ["account", "archived_account", "external_transaction"])
@pytest.mark.parametrize("change", [{"currency": "USD"}, {"precision": 3}])
def test_currency_and_precision_locked_by_connection_records(company_actor, record, change):
    company, actor = company_actor
    if record == "external_transaction":
        integration = Integration.objects.create(company=company, name="Paiement externe", kind="payments")
        ExternalTransaction.objects.create(company=company, integration=integration, external_id="external-1", amount="1", currency="EUR", date=date(2026, 9, 10))
    else:
        BankAccount.objects.create(company=company, name="Banque", currency="EUR", archived=record == "archived_account")
    with pytest.raises(DomainError, match="configuration_locked"):
        configure_company(company, actor, change)
    company.refresh_from_db()
    assert company.currency == "EUR" and company.precision == 2
    client = APIClient()
    client.force_authenticate(actor)
    response = client.patch("/api/company/", change, format="json")
    assert response.status_code == 409 and response.json()["code"] == "configuration_locked"
    updated = configure_company(company, actor, {"name": "Nom corrigé", "print_settings": {"layout": "compact"}, "currency": "EUR", "precision": 2})
    assert updated.name == "Nom corrigé" and updated.print_settings == {"layout": "compact"}


def test_other_company_accounts_do_not_lock_current_configuration(company_actor):
    company, actor = company_actor
    other = Company.objects.create(name="Autre société")
    BankAccount.objects.create(company=other, name="Autre banque", currency="EUR")
    company = configure_company(company, actor, {"currency": "USD", "precision": 3})
    assert company.currency == "USD" and company.precision == 3

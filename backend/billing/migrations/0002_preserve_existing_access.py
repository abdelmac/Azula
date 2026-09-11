from django.db import migrations


def preserve_existing_access(apps, schema_editor):
    """La mise à jour ne transforme pas les sociétés existantes en abonnés payants."""
    Company = apps.get_model("erp", "Company")
    Subscription = apps.get_model("billing", "Subscription")
    alias = schema_editor.connection.alias
    for company_id in Company.objects.using(alias).values_list("pk", flat=True).iterator():
        Subscription.objects.using(alias).get_or_create(company_id=company_id, defaults={"exempt": True})


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(preserve_existing_access, migrations.RunPython.noop)]

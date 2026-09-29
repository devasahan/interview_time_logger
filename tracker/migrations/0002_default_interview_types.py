from django.db import migrations

DEFAULT_TYPES = ["HR", "Technical", "Culture Call", "Hiring Manager", "Final Round", "Other"]


def add_default_types(apps, schema_editor):
    InterviewType = apps.get_model("tracker", "InterviewType")
    for name in DEFAULT_TYPES:
        InterviewType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0001_initial")]

    operations = [migrations.RunPython(add_default_types, migrations.RunPython.noop)]

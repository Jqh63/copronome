"""Relevés d'index en ajout seul au niveau de Postgres, même trigger que les
journaux (audit, migration 0002). Sans effet hors Postgres (SQLite des tests
locaux)."""

from django.db import migrations

TABLE = "eau_releve"


def poser(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"CREATE TRIGGER ajout_seul BEFORE UPDATE OR DELETE ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION copronome_ajout_seul()"
    )
    schema_editor.execute(
        f"CREATE TRIGGER ajout_seul_truncate BEFORE TRUNCATE ON {TABLE} "
        "FOR EACH STATEMENT EXECUTE FUNCTION copronome_ajout_seul()"
    )


def retirer(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS ajout_seul ON {TABLE}")
    schema_editor.execute(f"DROP TRIGGER IF EXISTS ajout_seul_truncate ON {TABLE}")


class Migration(migrations.Migration):
    dependencies = [
        ("eau", "0001_initial"),
        ("audit", "0002_ajout_seul_postgres"),  # crée la fonction copronome_ajout_seul()
    ]

    operations = [migrations.RunPython(poser, retirer)]

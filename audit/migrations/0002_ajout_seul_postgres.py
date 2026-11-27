"""Ajout seul au niveau de Postgres (ADR de conception, modèle de menace).

Un trigger refuse UPDATE, DELETE et TRUNCATE sur les trois journaux, même
par SQL brut ou `QuerySet.update()`. Conséquence voulue : un compte qui
figure dans un journal se désactive, il ne se supprime pas (la suppression
mettrait `auteur` à NULL dans les journaux d'incidents et d'échéances).

Limite : le propriétaire des tables peut retirer le trigger. Le rôle sous
lequel tourne l'app doit donc être distinct du propriétaire (étape suivante).
Sans effet hors Postgres (SQLite des tests locaux).
"""

from django.db import migrations

TABLES = ["audit_journalaudit", "incidents_evenement", "echeances_realisation"]

FONCTION = """
CREATE OR REPLACE FUNCTION copronome_ajout_seul() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'journal en ajout seul : % refusé sur %', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END
$$;
"""


def poser(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FONCTION, params=None)  # pas de %-formatage : le RAISE contient des %
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER ajout_seul BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION copronome_ajout_seul()"
        )
        schema_editor.execute(
            f"CREATE TRIGGER ajout_seul_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION copronome_ajout_seul()"
        )


def retirer(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS ajout_seul ON {table}")
        schema_editor.execute(f"DROP TRIGGER IF EXISTS ajout_seul_truncate ON {table}")
    schema_editor.execute("DROP FUNCTION IF EXISTS copronome_ajout_seul()")


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
        ("incidents", "0001_initial"),
        ("echeances", "0001_initial"),
    ]

    operations = [migrations.RunPython(poser, retirer)]

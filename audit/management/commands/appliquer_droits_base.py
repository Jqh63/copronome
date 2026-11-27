"""Crée ou met à jour le rôle Postgres de l'app et ses droits (ADR, menaces).

Lancé par le rôle propriétaire après `migrate` (service `migrer` du compose).
Le rôle de l'app n'est ni superutilisateur ni propriétaire : il ne peut ni
retirer les triggers d'ajout seul, ni modifier, supprimer ou vider les
journaux, ni changer le schéma. Idempotent : à rejouer à chaque déploiement,
les tables créées par une nouvelle migration reçoivent ainsi leurs droits.

manage.py appliquer_droits_base   (COPRONOME_DB_APP_USER, COPRONOME_DB_APP_PASSWORD)
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql

JOURNAUX = ["audit_journalaudit", "incidents_evenement", "echeances_realisation"]
LECTURE_SEULE = ["django_migrations"]


class Command(BaseCommand):
    help = "Crée le rôle Postgres de l'app et lui donne les seuls droits utiles."

    def handle(self, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Postgres seulement.")
        role = os.environ.get("COPRONOME_DB_APP_USER", "copronome_app")
        mot_de_passe = os.environ.get("COPRONOME_DB_APP_PASSWORD", "")
        if not mot_de_passe:
            raise CommandError("COPRONOME_DB_APP_PASSWORD manquant.")
        base = connection.settings_dict["NAME"]
        r = sql.Identifier(role)

        def executer(requete, *args):
            curseur.execute(requete.format(*args).as_string(connection.connection))

        with transaction.atomic(), connection.cursor() as curseur:
            curseur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            if curseur.fetchone() is None:
                executer(sql.SQL("CREATE ROLE {} LOGIN"), r)
            executer(
                sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}"),
                r,
                sql.Literal(mot_de_passe),
            )
            executer(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}"), sql.Identifier(base), r)
            executer(sql.SQL("GRANT USAGE ON SCHEMA public TO {}"), r)
            executer(sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}"), r)
            executer(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}"), r)
            executer(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"), r)
            executer(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}"), r)
            for table in JOURNAUX:
                executer(sql.SQL("REVOKE UPDATE, DELETE ON {} FROM {}"), sql.Identifier(table), r)
            for table in LECTURE_SEULE:
                executer(sql.SQL("REVOKE INSERT, UPDATE, DELETE ON {} FROM {}"), sql.Identifier(table), r)
        self.stdout.write(f"droits de base appliqués au rôle {role}")

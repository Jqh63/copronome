"""Donne au rôle Postgres de l'app ses seuls droits utiles (ADR, menaces).

Lancé par le rôle propriétaire après `migrate` (service `migrer` du compose).
Le rôle de l'app n'est ni superutilisateur ni propriétaire : il ne peut ni
retirer les triggers d'ajout seul, ni modifier, supprimer ou vider les
journaux, ni changer le schéma. Idempotent : à rejouer à chaque déploiement,
les tables créées par une nouvelle migration reçoivent ainsi leurs droits.

Le rôle est créé, avec son mot de passe, par le provisionnement de l'instance
(exploitation/postgres.py, superutilisateur du cluster) : le propriétaire,
qui n'est pas superutilisateur, ne peut pas le créer ni le modifier. La
commande refuse un rôle absent ou doté d'un attribut d'administration.

manage.py appliquer_droits_base   (COPRONOME_DB_APP_USER)
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql

JOURNAUX = ["audit_journalaudit", "incidents_evenement", "echeances_realisation", "eau_releve"]
LECTURE_SEULE = ["django_migrations"]


class Command(BaseCommand):
    help = "Crée le rôle Postgres de l'app et lui donne les seuls droits utiles."

    def handle(self, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Postgres seulement.")
        role = os.environ.get("COPRONOME_DB_APP_USER", "copronome_app")
        base = connection.settings_dict["NAME"]
        r = sql.Identifier(role)

        def executer(requete, *args):
            curseur.execute(requete.format(*args).as_string(connection.connection))

        with transaction.atomic(), connection.cursor() as curseur:
            curseur.execute(
                "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls"
                " FROM pg_roles WHERE rolname = %s",
                [role],
            )
            ligne = curseur.fetchone()
            if ligne is None:
                raise CommandError(f"rôle {role} absent : provisionner l'instance d'abord.")
            if ligne[0]:
                raise CommandError(f"rôle {role} doté d'un attribut d'administration : refusé.")
            if role == connection.settings_dict["USER"]:
                raise CommandError(f"rôle {role} = rôle propriétaire : refusé.")
            # Cluster partagé entre instances (ADR domaine et instances, § 2) :
            # seuls le propriétaire et le rôle de l'app se connectent à la base.
            executer(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC"), sql.Identifier(base))
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

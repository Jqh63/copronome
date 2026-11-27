"""Rôle Postgres de l'app : ni superutilisateur, ni propriétaire, journaux en
ajout seul par les droits (en plus du trigger). Postgres seulement (CI)."""

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection, transaction

from audit.management.commands.appliquer_droits_base import JOURNAUX
from audit.models import Action, journaliser

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="droits Postgres"),
]

ROLE = "copronome_app"


@pytest.fixture
def droits(monkeypatch):
    monkeypatch.setenv("COPRONOME_DB_APP_PASSWORD", "essai-ci")
    call_command("appliquer_droits_base")
    call_command("appliquer_droits_base")  # idempotent


def _a(table, droit):
    with connection.cursor() as c:
        c.execute("SELECT has_table_privilege(%s, %s, %s)", [ROLE, table, droit])
        return c.fetchone()[0]


def _en_tant_que_app(requete):
    with transaction.atomic(), connection.cursor() as c:
        c.execute(f"SET LOCAL ROLE {ROLE}")
        c.execute(requete)
        c.execute("RESET ROLE")  # en cas de succès : la suite du test reprend le rôle du banc


@pytest.mark.parametrize("table", JOURNAUX)
def test_journaux_en_ajout_seul_par_les_droits(droits, table):
    assert _a(table, "INSERT") and _a(table, "SELECT")
    for droit in ("UPDATE", "DELETE", "TRUNCATE"):
        assert not _a(table, droit), droit


def test_tables_ordinaires_modifiables_migrations_en_lecture(droits):
    assert _a("incidents_incident", "UPDATE") and _a("incidents_incident", "DELETE")
    assert not _a("incidents_incident", "TRUNCATE")
    assert _a("django_migrations", "SELECT") and not _a("django_migrations", "INSERT")


def test_role_sans_privilege_d_administration(droits):
    with connection.cursor() as c:
        c.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolcanlogin "
            "FROM pg_roles WHERE rolname = %s",
            [ROLE],
        )
        assert c.fetchone() == (False, False, False, False, True)


def test_l_app_ne_peut_ni_modifier_le_journal_ni_retirer_le_trigger(droits):
    journaliser(Action.CONNEXION, acteur_nom="x@example.org")
    with pytest.raises(DatabaseError, match="permission denied"):
        _en_tant_que_app("UPDATE audit_journalaudit SET acteur_nom = 'autre'")
    with pytest.raises(DatabaseError, match="must be owner"):
        _en_tant_que_app("DROP TRIGGER ajout_seul ON audit_journalaudit")
    with pytest.raises(DatabaseError, match="permission denied"):
        _en_tant_que_app("CREATE TABLE intrus (id int)")


def test_l_app_peut_inserer_au_journal(droits):
    # Contrôle positif : le refus ci-dessus vient des droits, pas du SET ROLE.
    _en_tant_que_app(
        "INSERT INTO audit_journalaudit (cree_le, acteur_nom, action, objet_type, objet_id, "
        "objet_libelle, detail) VALUES (now(), 'x', 'connexion', '', '', '', '{}')"
    )


def test_mot_de_passe_obligatoire(monkeypatch):
    monkeypatch.delenv("COPRONOME_DB_APP_PASSWORD", raising=False)
    with pytest.raises(CommandError):
        call_command("appliquer_droits_base")

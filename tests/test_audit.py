"""Journal d'audit : ajout seul (ORM et Postgres), et événements journalisés."""

import datetime

import pytest
from allauth.mfa import signals as mfa
from allauth.mfa.models import Authenticator
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from acces.models import Invitation, Role
from audit.models import Action, JournalAudit, journaliser
from documents.models import Document
from echeances.models import Echeance, realiser
from incidents.models import Evenement, Incident
from tests.test_acces import _compte
from tests.test_documents import PDF, _deposer

pytestmark = pytest.mark.django_db

postgres = pytest.mark.skipif(connection.vendor != "postgresql", reason="trigger propre à Postgres")


def _actions():
    return list(JournalAudit.objects.order_by("pk").values_list("action", flat=True))


# --- Ajout seul ---------------------------------------------------------------


def test_orm_refuse_modification_et_suppression():
    entree = journaliser(Action.CONNEXION, acteur_nom="x@example.org")
    entree.acteur_nom = "autre"
    with pytest.raises(ValidationError):
        entree.save()
    with pytest.raises(ValidationError):
        entree.delete()
    with pytest.raises(ValidationError):
        JournalAudit.objects.update(acteur_nom="autre")
    with pytest.raises(ValidationError):
        JournalAudit.objects.all().delete()


@postgres
@pytest.mark.parametrize("table", ["audit_journalaudit", "incidents_evenement", "echeances_realisation"])
@pytest.mark.parametrize(
    "requete",
    ["UPDATE {t} SET id = id", "DELETE FROM {t}", "TRUNCATE {t} CASCADE"],
)
def test_postgres_refuse_update_delete_truncate(table, requete):
    # Contrôle positif : la table a une ligne, sinon UPDATE et DELETE ne
    # déclencheraient pas le trigger de ligne et le test passerait à tort.
    if table == "audit_journalaudit":
        journaliser(Action.CONNEXION, acteur_nom="x@example.org")
    else:
        call_command("charger_demo")
        membre = _compte("cs@example.org", Role.MEMBRE_CS)
        _ligne_metier(table, membre)
    with connection.cursor() as curseur:
        # Noms de table = constantes du paramétrage, jamais une saisie.
        curseur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
        assert curseur.fetchone()[0] > 0
        # Clés étrangères différées : sans ceci, TRUNCATE serait refusé pour
        # « pending trigger events » et non par le trigger d'ajout seul.
        curseur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(DatabaseError, match="ajout seul"):
            with transaction.atomic():
                curseur.execute(requete.format(t=table))


def _ligne_metier(table, auteur):
    if table == "incidents_evenement":
        incident = Incident.objects.create(titre="Fuite", description="Cave")
        Evenement.objects.create(incident=incident, type=Evenement.Type.CREATION, auteur=auteur)
    else:
        echeance = Echeance.objects.create(titre="DPE", prochaine_le=datetime.date(2030, 1, 1))
        realiser(echeance, datetime.date(2029, 12, 1), auteur)


@postgres
def test_postgres_insertion_reste_permise():
    journaliser(Action.CONNEXION, acteur_nom="x@example.org")
    assert JournalAudit.objects.count() == 1


def test_suppression_du_compte_garde_le_nom_de_l_acteur():
    compte = _compte("ancien@example.org", mfa=False)
    journaliser(Action.CONNEXION, acteur=compte)
    compte.delete()
    entree = JournalAudit.objects.get(action=Action.CONNEXION)
    assert entree.acteur_nom == "ancien@example.org"


# --- Événements journalisés -------------------------------------------------


def test_connexion_et_deconnexion(client):
    compte = _compte("cs@example.org", mfa=False)
    client.force_login(compte)
    client.post(reverse("account_logout"))
    assert _actions() == [Action.CONNEXION, Action.DECONNEXION]
    assert set(JournalAudit.objects.values_list("acteur_nom", flat=True)) == {"cs@example.org"}


def test_echec_de_connexion_garde_l_identifiant_jamais_le_mot_de_passe():
    _compte("cs@example.org", mfa=False)
    assert authenticate(None, email="cs@example.org", password="mauvais-secret") is None
    entree = JournalAudit.objects.get()
    assert entree.action == Action.CONNEXION_ECHEC
    assert entree.acteur is None
    assert entree.acteur_nom == "cs@example.org"
    assert "mauvais-secret" not in str(entree.detail)


def test_second_facteur_ajoute_et_retire():
    compte = _compte("cs@example.org", mfa=False)
    totp = Authenticator.objects.create(user=compte, type=Authenticator.Type.TOTP, data={"secret": "x"})
    mfa.authenticator_added.send(sender=Authenticator, request=None, user=compte, authenticator=totp)
    mfa.authenticator_removed.send(sender=Authenticator, request=None, user=compte, authenticator=totp)
    assert _actions() == [Action.SECOND_FACTEUR_AJOUTE, Action.SECOND_FACTEUR_RETIRE]
    assert JournalAudit.objects.first().detail == {"type": "totp"}


def test_invitation_creee_puis_acceptee_sans_jeton_au_journal(client):
    admin = _compte("admin@example.org", Role.ADMIN)
    invitation, jeton = Invitation.creer("nouveau@example.org", Role.COPROPRIETAIRE, creee_par=admin)
    reponse = client.post(
        reverse("accepter_invitation", args=[jeton]),
        {"mot_de_passe": "Un-mot-de-passe-long-2026", "confirmation": "Un-mot-de-passe-long-2026"},
    )
    assert reponse.status_code == 302, reponse.content
    creee, acceptee = (
        JournalAudit.objects.get(action=Action.INVITATION_CREEE),
        JournalAudit.objects.get(action=Action.INVITATION_ACCEPTEE),
    )
    assert creee.acteur == admin and creee.objet_id == str(invitation.pk)
    assert acceptee.acteur_nom == "nouveau@example.org"
    for entree in JournalAudit.objects.all():
        assert jeton not in str(entree.detail) and jeton not in entree.objet_libelle


def test_depot_de_document_journalise_avec_son_empreinte(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("charger_demo")
    membre = _compte("cs@example.org", Role.MEMBRE_CS)
    client.force_login(membre)
    assert _deposer(client, PDF).status_code == 302
    document = Document.objects.get()
    entree = JournalAudit.objects.get(action=Action.DOCUMENT_DEPOSE)
    assert entree.acteur == membre
    assert entree.objet_type == "documents.document" and entree.objet_id == str(document.pk)
    assert entree.detail["empreinte"] == document.empreinte


def test_depot_refuse_ne_journalise_rien(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("charger_demo")
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    assert _deposer(client, b"<html></html>", nom="x.pdf").status_code == 400
    assert not JournalAudit.objects.filter(action=Action.DOCUMENT_DEPOSE).exists()

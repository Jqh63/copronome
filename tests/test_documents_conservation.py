"""Conservation : un document valide ou dans sa durée ne se retire pas, sauf
erreur de dépôt sous 48 h ou effacement imposé (documents/conservation.py)."""

from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from acces.models import Role
from documents.conservation import REGLES, echeance
from documents.models import Categorie, Document
from tests.test_acces import _compte
from tests.test_documents import PDF, _deposer
from tests.test_documents_retrait import _remplacer, _retirer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def membre(client):
    call_command("charger_demo")
    compte = _compte("cs@example.org", Role.MEMBRE_CS)
    client.force_login(compte)
    return compte


def _vieillir(document, **delta):
    Document.objects.filter(pk=document.pk).update(depose_le=timezone.now() - timedelta(**delta))
    document.refresh_from_db()
    return document


def _dernier():
    return Document.objects.latest("pk")


def test_toute_categorie_a_une_regle_justifiee():
    for valeur, _ in Categorie.choices:
        assert valeur in REGLES and REGLES[valeur].justification


def test_echeance_selon_le_point_de_depart():
    devis = Document(categorie=Categorie.DEVIS, date_document=date(2024, 2, 29), depose_le=timezone.now())
    assert echeance(devis).jusquau == date(2029, 2, 28)
    contrat = Document(categorie=Categorie.ASSURANCE, depose_le=timezone.now())
    assert echeance(contrat).libelle == "Fin de validité à saisir"
    contrat.valide_jusquau = date(2020, 1, 1)
    assert echeance(contrat).jusquau == date(2025, 1, 1)
    assert echeance(Document(categorie=Categorie.PV_AG, depose_le=timezone.now())).sans_limite


def test_fin_de_conservation_refusee_tant_que_le_document_est_conserve(client, membre):
    _deposer(client, PDF, categorie=Categorie.PV_AG)
    pv = _vieillir(_dernier(), days=400)
    reponse = _retirer(client, pv, motif="Ménage", raison="fin")
    assert reponse.status_code == 409
    assert "conservé" in reponse.content.decode()
    pv.refresh_from_db()
    assert pv.retire_le is None and pv.fichier.storage.exists(pv.fichier.name)


def test_fin_de_conservation_permise_une_fois_la_duree_passee(client, membre):
    _deposer(client, PDF, categorie=Categorie.DEVIS, date_document="2015-01-10")
    devis = _vieillir(_dernier(), days=4000)
    assert _retirer(client, devis, motif="Durée passée", raison="fin").status_code == 302
    devis.refresh_from_db()
    assert devis.retire_le is not None


def test_erreur_de_depot_permise_sous_48_h_seulement(client, membre):
    _deposer(client, PDF, categorie=Categorie.PV_AG)
    recent = _dernier()
    assert _retirer(client, recent, motif="Mauvais fichier", raison="erreur").status_code == 302
    _deposer(client, PDF, categorie=Categorie.PV_AG)
    ancien = _vieillir(_dernier(), hours=49)
    reponse = _retirer(client, ancien, motif="Mauvais fichier", raison="erreur")
    assert reponse.status_code == 409 and "48 h" in reponse.content.decode()


def test_erreur_refusee_si_elle_emporterait_une_version_conservee(client, membre):
    _deposer(client, PDF, categorie=Categorie.PV_AG)
    _vieillir(_dernier(), days=400)
    _remplacer(client, _dernier())
    nouvelle = _dernier()
    reponse = _retirer(client, nouvelle, motif="Mauvais fichier", raison="erreur")
    assert reponse.status_code == 409 and "Remplacer" in reponse.content.decode()
    assert nouvelle.remplace.retire_le is None


def test_effacement_impose_toujours_possible_et_journalise(client, membre):
    from audit.models import Action, JournalAudit

    _deposer(client, PDF, categorie=Categorie.PV_AG)
    pv = _vieillir(_dernier(), days=400)
    assert _retirer(client, pv, motif="Demande d'effacement RGPD", raison="effacement").status_code == 302
    entree = JournalAudit.objects.filter(action=Action.DOCUMENT_RETIRE).latest("pk")
    assert entree.detail["raison"] == "effacement"


def test_liste_et_page_de_retrait_affichent_la_conservation(client, membre):
    _deposer(client, PDF, categorie=Categorie.PV_AG)
    pv = _dernier()
    assert "Sans limite" in client.get("/documents/").content.decode()
    assert "art. 33" in client.get(f"/documents/{pv.pk}/retirer/").content.decode()

"""Consultation et export du journal d'audit : droits, filtres, export
journalisé, neutralisation des formules dans le CSV."""

import csv
import io

import pytest
from django.urls import reverse

from acces.models import Role
from audit.models import Action, JournalAudit, journaliser
from audit.views import PAR_PAGE
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db

ATTENDU = {
    Role.ADMIN: 200,
    Role.PRESIDENT: 200,
    Role.MEMBRE_CS: 403,
    Role.CONTROLEUR: 403,
    Role.SYNDIC_NON_PRO: 200,
    Role.SYNDIC: 403,
    Role.COPROPRIETAIRE: 403,
}


@pytest.mark.parametrize("role", list(Role))
def test_matrice_role(client, role):
    assert set(ATTENDU) == set(Role), "chaque rôle doit avoir son attendu"
    client.force_login(_compte(f"{role}@example.org", role))
    assert client.get(reverse("audit:journal")).status_code == ATTENDU[role]
    assert client.get(reverse("audit:exporter")).status_code == ATTENDU[role]
    if ATTENDU[role] == 403:
        assert not JournalAudit.objects.filter(action=Action.JOURNAL_EXPORTE).exists()


@pytest.fixture
def president(client):
    compte = _compte("president@example.org", Role.PRESIDENT)
    client.force_login(compte)
    return compte


def test_filtres(client, president):
    journaliser(Action.CONNEXION_ECHEC, acteur_nom="intrus@example.org")
    journaliser(Action.DOCUMENT_DEPOSE, acteur=president)
    url = reverse("audit:journal")
    actions = {e.action for e in client.get(url, {"action": Action.CONNEXION_ECHEC}).context["page"]}
    assert actions == {Action.CONNEXION_ECHEC}
    noms = {e.acteur_nom for e in client.get(url, {"acteur": "INTRUS"}).context["page"]}
    assert noms == {"intrus@example.org"}
    assert list(client.get(url, {"du": "2999-01-01"}).context["page"]) == []
    assert client.get(url, {"du": "pas une date"}).status_code == 400


def test_pagination_garde_les_filtres(client, president):
    for _ in range(PAR_PAGE + 1):
        journaliser(Action.CONNEXION_ECHEC, acteur_nom="x@example.org")
    page = client.get(reverse("audit:journal"), {"action": Action.CONNEXION_ECHEC}).content.decode()
    assert "action=connexion_echec&amp;page=2" in page


def _lire_csv(reponse):
    texte = reponse.content.decode("utf-8")
    assert texte.startswith("﻿")
    return list(csv.reader(io.StringIO(texte[1:]), delimiter=";"))


def test_export_csv_journalise_et_neutralise_les_formules(client, president):
    # Identifiant tenté à la connexion = saisie libre d'un anonyme.
    piege = '=HYPERLINK("http://exemple.invalid","clic")'
    journaliser(Action.CONNEXION_ECHEC, acteur_nom=piege)
    journaliser(Action.DOCUMENT_DEPOSE, acteur=president, empreinte="ab" * 32)
    reponse = client.get(reverse("audit:exporter"), {"action": Action.CONNEXION_ECHEC})
    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "text/csv; charset=utf-8"
    assert reponse["Content-Disposition"].startswith('attachment; filename="journal-audit-')
    assert reponse["Cache-Control"] == "private, no-store"
    lignes = _lire_csv(reponse)
    assert lignes[0] == ["date", "acteur", "action", "objet_type", "objet_id", "objet", "detail"]
    assert len(lignes) == 2  # filtre appliqué
    assert lignes[1][1] == "'" + piege
    assert lignes[1][2] == "Échec de connexion"
    # L'export est lui-même au journal, avec ses filtres et son volume.
    export = JournalAudit.objects.get(action=Action.JOURNAL_EXPORTE)
    assert export.acteur == president
    assert export.detail == {"filtres": {"action": "connexion_echec"}, "lignes": 1}


def test_export_refuse_un_filtre_invalide(client, president):
    assert client.get(reverse("audit:exporter"), {"au": "x"}).status_code == 400
    assert not JournalAudit.objects.filter(action=Action.JOURNAL_EXPORTE).exists()

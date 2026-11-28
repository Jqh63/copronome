"""Identité de l'instance (ADR domaine et instances, § 4) : un seul
enregistrement, affiché dans les pages, les mails et l'iCal."""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.urls import reverse

from acces.models import Affectation, Role
from agenda.models import JetonAgenda
from copro.identite import expediteur, nom_affiche
from copro.models import Copropriete

pytestmark = pytest.mark.django_db


def _identite(**champs):
    valeurs = {"nom": "Les Tilleuls", "commune": "Exempleville", "code_insee": "99999"} | champs
    return Copropriete.objects.create(**valeurs)


def test_sans_identite_le_nom_affiche_est_le_produit(client):
    assert nom_affiche() == "Copronome"
    assert "<title>Copronome</title>" in client.get("/").content.decode()


def test_un_seul_enregistrement():
    _identite()
    with pytest.raises(IntegrityError):
        Copropriete.objects.create(id=2, nom="Autre", commune="X", code_insee="99998")


def test_nom_et_commune_dans_les_pages(client):
    _identite(adresse="1 rue de l'Exemple", immatriculation="DEMO-0001")
    corps = client.get("/").content.decode()
    assert "Les Tilleuls (Exempleville)" in corps
    # Adresse et immatriculation : comptes connectés seulement.
    assert "rue de l&#x27;Exemple" not in corps and "DEMO-0001" not in corps
    compte = get_user_model().objects.create_user("p", "p@example.org", "x" * 12)
    Affectation.objects.create(utilisateur=compte, role=Role.COPROPRIETAIRE)
    client.force_login(compte)
    corps = client.get("/").content.decode()
    assert "DEMO-0001" in corps and "99999" in corps


def test_expediteur_porte_le_nom_de_la_copropriete(settings):
    settings.DEFAULT_FROM_EMAIL = "envoi@example.org"
    assert expediteur() == "Copronome <envoi@example.org>"
    _identite()
    assert expediteur() == "Les Tilleuls via Copronome <envoi@example.org>"


def test_invitation_au_nom_de_la_copropriete(settings):
    settings.DEFAULT_FROM_EMAIL = "envoi@example.org"
    _identite()
    call_command("inviter", "x@example.org", Role.MEMBRE_CS)
    (message,) = mail.outbox
    assert "Les Tilleuls (Exempleville)" in message.subject
    assert message.from_email == "Les Tilleuls via Copronome <envoi@example.org>"


def test_ical_nomme_le_calendrier(client):
    _identite()
    compte = get_user_model().objects.create_user("c", "c@example.org", "x" * 12)
    Affectation.objects.create(utilisateur=compte, role=Role.COPROPRIETAIRE)
    jeton = JetonAgenda.generer(compte)
    corps = client.get(reverse("agenda:ical", args=[jeton])).content.decode()
    assert "X-WR-CALNAME:Les Tilleuls (Exempleville)" in corps


def test_commande_idempotente_et_validee():
    call_command("copropriete", nom="Les Tilleuls", commune="Exempleville", code_insee="2A004")
    call_command("copropriete", immatriculation="DEMO-0002")
    assert Copropriete.objects.count() == 1
    assert Copropriete.courante().immatriculation == "DEMO-0002"
    with pytest.raises(CommandError, match="code_insee"):
        call_command("copropriete", code_insee="63")

"""Agenda : droits et périmètre, lien iCal (jeton haché, révocation, compte
désactivé ou sans second facteur), format iCalendar."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from acces.models import Role, empreinte
from agenda.ical import _plier, calendrier
from agenda.models import Evenement, JetonAgenda
from copro.models import Batiment
from echeances.models import Echeance
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db


@pytest.fixture
def demo():
    call_command("charger_demo")


def _evenement(titre="Réunion du CS", batiment=None, dans_jours=3):
    return Evenement.objects.create(
        titre=titre, debut=timezone.now() + datetime.timedelta(days=dans_jours), batiment=batiment
    )


def _flux(client, jeton):
    return client.get(reverse("agenda:ical", args=[jeton]))


ATTENDU = {
    Role.ADMIN: (200, 403),
    Role.PRESIDENT: (200, 302),
    Role.MEMBRE_CS: (200, 302),
    Role.CONTROLEUR: (403, 403),
    Role.SYNDIC_NON_PRO: (200, 302),
    Role.SYNDIC: (403, 403),
    Role.COPROPRIETAIRE: (403, 403),
}


@pytest.mark.parametrize("role", list(Role))
def test_matrice_role_agenda(client, demo, role):
    assert set(ATTENDU) == set(Role), "chaque rôle doit avoir son attendu"
    client.force_login(_compte(f"{role}@example.org", role))
    lecture, ecriture = ATTENDU[role]
    assert client.get(reverse("agenda:liste")).status_code == lecture
    debut = (timezone.localtime() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    assert client.post(reverse("agenda:creer"), {"titre": "AG", "debut": debut}).status_code == ecriture


def test_perimetre_batiment(client, demo):
    a, b = Batiment.objects.get(nom="Bâtiment A"), Batiment.objects.get(nom="Bâtiment B")
    ev_a, ev_b, commun = _evenement("A", a), _evenement("B", b), _evenement("Commun")
    client.force_login(_compte("cs-a@example.org", Role.MEMBRE_CS, batiment=a))
    assert set(client.get(reverse("agenda:liste")).context["evenements"]) == {ev_a, commun}
    assert client.get(reverse("agenda:modifier", args=[ev_b.pk])).status_code == 403


def test_lien_ical_hache_affiche_une_fois_et_flux_filtre(client, demo):
    a, b = Batiment.objects.get(nom="Bâtiment A"), Batiment.objects.get(nom="Bâtiment B")
    _evenement("Visite ascenseur A", a)
    _evenement("Visite ascenseur B", b)
    Echeance.objects.create(
        titre="Contrat d'entretien", type=Echeance.Type.CONTRAT, prochaine_le=timezone.localdate(), batiment=a
    )
    membre = _compte("cs-a@example.org", Role.MEMBRE_CS, batiment=a)
    client.force_login(membre)
    page = client.post(reverse("agenda:lien_ical"))
    jeton = page.context["lien"].rstrip("/").rsplit("/", 1)[1]
    assert JetonAgenda.objects.get().empreinte_jeton == empreinte(jeton)
    assert jeton not in JetonAgenda.objects.get().empreinte_jeton
    client.logout()
    reponse = _flux(client, jeton)
    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "text/calendar; charset=utf-8"
    assert reponse["Cache-Control"] == "private, no-store"
    corps = reponse.content.decode()
    assert "Visite ascenseur A" in corps and "Visite ascenseur B" not in corps
    assert "SUMMARY:Échéance : Contrat d'entretien" in corps
    assert corps.startswith("BEGIN:VCALENDAR\r\n") and corps.endswith("END:VCALENDAR\r\n")


def test_nouveau_lien_revoque_l_ancien_et_suppression(client, demo):
    membre = _compte("cs@example.org", Role.MEMBRE_CS)
    ancien = JetonAgenda.generer(membre)
    nouveau = JetonAgenda.generer(membre)
    assert _flux(client, ancien).status_code == 404
    assert _flux(client, nouveau).status_code == 200
    client.force_login(membre)
    client.post(reverse("agenda:lien_ical"), {"revoquer": "1"})
    client.logout()
    assert _flux(client, nouveau).status_code == 404


def test_jeton_inconnu(client):
    assert _flux(client, "inconnu").status_code == 404


def test_compte_desactive_ou_sans_second_facteur(client, demo):
    membre = _compte("cs@example.org", Role.MEMBRE_CS)
    jeton = JetonAgenda.generer(membre)
    Authenticator.objects.filter(user=membre).delete()
    assert _flux(client, jeton).status_code == 404
    Authenticator.objects.create(user=membre, type=Authenticator.Type.TOTP, data={"secret": "x"})
    assert _flux(client, jeton).status_code == 200
    membre.is_active = False
    membre.save()
    assert _flux(client, jeton).status_code == 404


def test_flux_d_un_role_sans_droit_est_vide(client, demo):
    _evenement("Réunion")
    jeton = JetonAgenda.generer(_compte("syndic@example.org", Role.SYNDIC))
    corps = _flux(client, jeton).content.decode()
    assert "BEGIN:VEVENT" not in corps


def test_fin_avant_debut_refusee(client, demo):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    reponse = client.post(
        reverse("agenda:creer"), {"titre": "x", "debut": "2027-01-02T10:00", "fin": "2027-01-02T09:00"}
    )
    assert reponse.status_code == 400 and not Evenement.objects.exists()


def test_format_icalendar_echappement_et_pliage():
    corps = calendrier(
        "Copronome",
        [
            {
                "uid": "x@copronome",
                "titre": "AG; budget, travaux\\n",
                "debut": datetime.datetime(2027, 3, 1, 18, 30, tzinfo=datetime.UTC),
                "description": "ligne 1\nligne 2",
                "annule": True,
            },
            {"uid": "y@copronome", "titre": "Échéance", "debut": datetime.date(2027, 3, 31)},
        ],
    )
    assert "SUMMARY:AG\\; budget\\, travaux\\\\n\r\n" in corps
    assert "DESCRIPTION:ligne 1\\nligne 2\r\n" in corps
    assert "DTSTART:20270301T183000Z\r\n" in corps and "STATUS:CANCELLED\r\n" in corps
    assert "DTSTART;VALUE=DATE:20270331\r\nDTEND;VALUE=DATE:20270401\r\n" in corps
    longue = "SUMMARY:" + "é" * 100
    pliee = _plier(longue)
    assert all(len(ligne.encode()) <= 75 for ligne in pliee.split("\r\n"))
    assert pliee.replace("\r\n ", "") == longue

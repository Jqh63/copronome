import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from acces.models import Role
from copro.models import Batiment, Lot
from incidents.models import Evenement, Incident, Statut, journaliser
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db


@pytest.fixture
def demo():
    call_command("charger_demo")


@pytest.fixture
def incident_b(demo):
    incident = Incident.objects.create(titre="Fuite B", description="x", lot=Lot.objects.get(numero="B01"))
    incident.full_clean()
    incident.save()
    journaliser(incident, Evenement.Type.CREATION, None)
    return incident


def test_batiment_deduit_de_la_localisation(incident_b):
    assert incident_b.batiment.nom == "Bâtiment B"


def test_localisation_incoherente_refusee(demo):
    incident = Incident(
        titre="x",
        description="x",
        batiment=Batiment.objects.get(nom="Bâtiment A"),
        lot=Lot.objects.get(numero="B01"),
    )
    with pytest.raises(ValidationError, match="autre bâtiment"):
        incident.full_clean()


def test_journal_en_ajout_seul(incident_b):
    evenement = incident_b.evenements.get()
    evenement.texte = "réécrit"
    with pytest.raises(ValidationError):
        evenement.save()
    with pytest.raises(ValidationError):
        evenement.delete()
    with pytest.raises(ValidationError):
        Evenement.objects.all().update(texte="réécrit")
    with pytest.raises(ValidationError):
        Evenement.objects.all().delete()


def test_transmission_impose_le_statut_et_la_date(incident_b):
    journaliser(incident_b, Evenement.Type.TRANSMISSION, None, texte="Envoyé par mail")
    incident_b.refresh_from_db()
    assert incident_b.statut == Statut.TRANSMIS
    assert incident_b.transmis_syndic_le is not None


def test_changement_de_statut_sans_statut_refuse(incident_b):
    with pytest.raises(ValidationError):
        journaliser(incident_b, Evenement.Type.STATUT, None)


ATTENDU = {  # (lire la liste, créer)
    Role.ADMIN: (200, 403),
    Role.PRESIDENT: (200, 200),
    Role.MEMBRE_CS: (200, 200),
    Role.CONTROLEUR: (403, 403),
    Role.SYNDIC_NON_PRO: (200, 200),
    Role.SYNDIC: (403, 403),
    Role.COPROPRIETAIRE: (403, 403),
}


@pytest.mark.parametrize("role", list(Role))
def test_matrice_role_incidents(client, incident_b, role):
    assert set(ATTENDU) == set(Role)
    client.force_login(_compte(f"{role}@example.org", role))
    lire, creer = ATTENDU[role]
    assert client.get(reverse("incidents:liste")).status_code == lire
    assert client.get(reverse("incidents:detail", args=[incident_b.pk])).status_code == lire
    assert client.get(reverse("incidents:creer")).status_code == creer
    reponse = client.post(
        reverse("incidents:ajouter_evenement", args=[incident_b.pk]), {"type": "commentaire", "texte": "vu"}
    )
    assert reponse.status_code == (302 if creer == 200 else 403)


def test_membre_d_un_batiment_ne_voit_ni_ne_commente_un_autre_batiment(client, incident_b):
    membre_a = _compte(
        "membre-a@example.org", Role.MEMBRE_CS, batiment=Batiment.objects.get(nom="Bâtiment A")
    )
    client.force_login(membre_a)
    assert "Fuite B" not in client.get(reverse("incidents:liste")).content.decode()
    assert client.get(reverse("incidents:detail", args=[incident_b.pk])).status_code == 403
    reponse = client.post(
        reverse("incidents:ajouter_evenement", args=[incident_b.pk]), {"type": "commentaire", "texte": "x"}
    )
    assert reponse.status_code == 403
    assert incident_b.evenements.count() == 1


def test_membre_d_un_batiment_ne_cree_pas_ailleurs(client, demo):
    membre_a = _compte(
        "membre-a@example.org", Role.MEMBRE_CS, batiment=Batiment.objects.get(nom="Bâtiment A")
    )
    client.force_login(membre_a)
    lot_b = Lot.objects.get(numero="B01")
    reponse = client.post(
        reverse("incidents:creer"), {"titre": "x", "description": "x", "priorite": "normale", "lot": lot_b.pk}
    )
    assert reponse.status_code == 200  # formulaire refusé : lot hors périmètre
    assert not Incident.objects.exists()


def test_creation_puis_parcours_complet(client, demo):
    client.force_login(_compte("membre@example.org", Role.MEMBRE_CS))
    lot = Lot.objects.get(numero="A02")
    reponse = client.post(
        reverse("incidents:creer"),
        {"titre": "Ampoule hall", "description": "Grillée", "priorite": "basse", "lot": lot.pk},
    )
    incident = Incident.objects.get()
    assert reponse["Location"] == reverse("incidents:detail", args=[incident.pk])
    url = reverse("incidents:ajouter_evenement", args=[incident.pk])
    client.post(url, {"type": "transmission", "texte": "Mail au syndic"})
    client.post(url, {"type": "statut", "nouveau_statut": "resolu"})
    incident.refresh_from_db()
    assert incident.statut == Statut.RESOLU
    assert list(incident.evenements.values_list("type", flat=True)) == ["creation", "transmission", "statut"]
    assert client.post(url, {"type": "statut"}).status_code == 400


def test_le_signalant_n_est_pas_affiche_dans_la_liste(client, demo):
    signalant = _compte("discret@example.org", Role.MEMBRE_CS)
    Incident.objects.create(titre="Bruit", description="x", signale_par=signalant)
    client.force_login(_compte("autre@example.org", Role.MEMBRE_CS))
    assert "discret@example.org" not in client.get(reverse("incidents:liste")).content.decode()

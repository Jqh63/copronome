"""Échéances : report par réalisation, journal en ajout seul, rappels mail
idempotents et bornés au périmètre, droits rôle par rôle."""

import datetime
import re

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from acces.models import Role
from copro.models import Batiment
from echeances.controles_types import CONTROLES_TYPES
from echeances.models import Echeance, Realisation, ajouter_mois, realiser
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db
JOUR = datetime.timedelta(days=1)


@pytest.fixture
def demo():
    call_command("charger_demo")


def _echeance(titre="Contrôle ascenseur", dans=10, periodicite=60, rappel=30, batiment=None):
    return Echeance.objects.create(
        titre=titre,
        type=Echeance.Type.CONTROLE,
        prochaine_le=timezone.localdate() + dans * JOUR,
        periodicite_mois=periodicite,
        rappel_jours=rappel,
        batiment=batiment,
    )


@pytest.mark.parametrize(
    "depart, mois, attendu",
    [
        (datetime.date(2026, 1, 31), 1, datetime.date(2026, 2, 28)),
        (datetime.date(2028, 1, 31), 1, datetime.date(2028, 2, 29)),
        (datetime.date(2026, 11, 15), 2, datetime.date(2027, 1, 15)),
        (datetime.date(2026, 5, 10), 60, datetime.date(2031, 5, 10)),
    ],
)
def test_ajouter_mois(depart, mois, attendu):
    assert ajouter_mois(depart, mois) == attendu


def test_realisation_reporte_depuis_la_date_de_realisation(demo):
    echeance = _echeance(dans=5, periodicite=12)
    faite = timezone.localdate() - 2 * JOUR
    realiser(echeance, faite, None, note="PV reçu")
    echeance.refresh_from_db()
    assert echeance.prochaine_le == ajouter_mois(faite, 12)
    assert echeance.active
    assert echeance.realisations.get().pour_echeance_du == timezone.localdate() + 5 * JOUR


def test_echeance_ponctuelle_close_apres_realisation(demo):
    echeance = _echeance(periodicite=None)
    realiser(echeance, timezone.localdate(), None)
    echeance.refresh_from_db()
    assert not echeance.active
    with pytest.raises(ValidationError, match="close"):
        realiser(echeance, timezone.localdate(), None)


def test_journal_des_realisations_en_ajout_seul(demo):
    realisation = realiser(_echeance(), timezone.localdate(), None)
    realisation.note = "réécrite"
    with pytest.raises(ValidationError):
        realisation.save()
    with pytest.raises(ValidationError):
        realisation.delete()
    with pytest.raises(ValidationError):
        Realisation.objects.all().update(note="x")
    with pytest.raises(ValidationError):
        Realisation.objects.all().delete()


def test_rappel_envoye_une_seule_fois_par_echeance(demo):
    _compte("cs@example.org", Role.MEMBRE_CS)
    _echeance("Dans la fenêtre", dans=10, rappel=30)
    _echeance("Hors fenêtre", dans=60, rappel=30)
    _echeance("En retard", dans=-3)
    call_command("envoyer_rappels", url="https://copro.example.org")
    assert len(mail.outbox) == 1
    corps = mail.outbox[0].body
    assert "Dans la fenêtre" in corps and "En retard" in corps and "EN RETARD" in corps
    assert "Hors fenêtre" not in corps
    assert "https://copro.example.org/echeances/" in corps
    call_command("envoyer_rappels")
    assert len(mail.outbox) == 1, "relancer le même jour n'envoie rien"


def test_rappel_repart_apres_report(demo):
    _compte("cs@example.org", Role.MEMBRE_CS)
    echeance = _echeance(dans=10, periodicite=1, rappel=40)
    call_command("envoyer_rappels")
    realiser(echeance, timezone.localdate(), None)
    call_command("envoyer_rappels")
    assert len(mail.outbox) == 2, "la nouvelle date a son propre rappel"


def test_rappel_reserve_a_qui_peut_agir_dans_son_perimetre(demo):
    a, b = Batiment.objects.get(nom="Bâtiment A"), Batiment.objects.get(nom="Bâtiment B")
    _compte("admin@example.org", Role.ADMIN)
    _compte("controleur@example.org", Role.CONTROLEUR)
    _compte("cs-a@example.org", Role.MEMBRE_CS, batiment=a)
    ascenseur_b = _echeance("Ascenseur B", batiment=b)
    _echeance("Assurance commune")
    call_command("envoyer_rappels")
    # Seul le membre du bâtiment A agit : il reçoit l'échéance commune, pas celle de B.
    assert [(m.to, "Assurance commune" in m.body, "Ascenseur B" in m.body) for m in mail.outbox] == [
        (["cs-a@example.org"], True, False)
    ]
    ascenseur_b.refresh_from_db()
    assert ascenseur_b.rappel_envoye_pour is None, "sans destinataire, le rappel repart demain"
    _compte("cs-b@example.org", Role.MEMBRE_CS, batiment=b)
    call_command("envoyer_rappels")
    assert [m.to for m in mail.outbox[1:]] == [["cs-b@example.org"]]


ATTENDU_LISTE = {
    Role.ADMIN: 200,
    Role.PRESIDENT: 200,
    Role.MEMBRE_CS: 200,
    Role.CONTROLEUR: 403,
    Role.SYNDIC: 403,
    Role.COPROPRIETAIRE: 403,
}


@pytest.mark.parametrize("role", list(Role))
def test_matrice_role_echeances(client, demo, role):
    assert set(ATTENDU_LISTE) == set(Role), "chaque rôle doit avoir son attendu"
    echeance = _echeance()
    client.force_login(_compte(f"{role}@example.org", role))
    assert client.get(reverse("echeances:liste")).status_code == ATTENDU_LISTE[role]
    ecrit = client.post(reverse("echeances:realiser", args=[echeance.pk]), {"realisee_le": "2026-01-01"})
    peut_ecrire = role in (Role.PRESIDENT, Role.MEMBRE_CS)
    assert ecrit.status_code == (302 if peut_ecrire else 403)
    assert Realisation.objects.exists() == peut_ecrire


def test_perimetre_batiment(client, demo):
    a, b = Batiment.objects.get(nom="Bâtiment A"), Batiment.objects.get(nom="Bâtiment B")
    e_a, e_b, commune = _echeance("A", batiment=a), _echeance("B", batiment=b), _echeance("Commune")
    client.force_login(_compte("cs-a@example.org", Role.MEMBRE_CS, batiment=a))
    assert set(client.get(reverse("echeances:liste")).context["echeances"]) == {e_a, commune}
    assert client.get(reverse("echeances:detail", args=[e_b.pk])).status_code == 403
    assert (
        client.post(reverse("echeances:realiser", args=[e_b.pk]), {"realisee_le": "2026-01-01"}).status_code
        == 403
    )


def test_creation_puis_realisation_par_l_interface(client, demo):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    reponse = client.post(
        reverse("echeances:creer"),
        {
            "titre": "Contrat d'entretien",
            "type": Echeance.Type.CONTRAT,
            "prochaine_le": "2027-03-01",
            "periodicite_mois": "",
            "rappel_jours": "60",
            "reference": "Contrat n° 0000",
        },
    )
    echeance = Echeance.objects.get()
    assert reponse.status_code == 302 and echeance.periodicite_mois is None
    futur = (timezone.localdate() + JOUR).isoformat()
    assert (
        client.post(reverse("echeances:realiser", args=[echeance.pk]), {"realisee_le": futur}).status_code
        == 400
    )
    client.post(reverse("echeances:realiser", args=[echeance.pk]), {"realisee_le": "2026-11-01"})
    echeance.refresh_from_db()
    assert not echeance.active


# Bibliothèque de contrôles types : chaque modèle porte sa source officielle.
SOURCE_OFFICIELLE = re.compile(r"service-public\.gouv\.fr F\d+|CCH art\. [LR]\d|Loi 65-557 art\.")


def test_controles_types_sources_et_valeurs():
    codes = [controle.code for controle in CONTROLES_TYPES]
    assert len(codes) == len(set(codes))
    for controle in CONTROLES_TYPES:
        assert SOURCE_OFFICIELLE.search(controle.reference), controle.code
        assert controle.type in Echeance.Type.values
        assert controle.periodicite_mois > 0
        Echeance(**controle.initial(), prochaine_le=timezone.localdate()).full_clean()


def test_modele_pre_remplit_sans_rien_creer(client, demo):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    reponse = client.get(reverse("echeances:creer"), {"modele": "dpe-collectif"})
    assert reponse.status_code == 200
    initial = reponse.context["form"].initial
    assert initial["periodicite_mois"] == 120 and "L126-31" in initial["reference"]
    assert "prochaine_le" not in initial
    assert not Echeance.objects.exists()
    assert client.get(reverse("echeances:creer"), {"modele": "inconnu"}).status_code == 404


def test_modele_reserve_a_qui_peut_ecrire(client, demo):
    client.force_login(_compte("copro@example.org", Role.COPROPRIETAIRE))
    assert client.get(reverse("echeances:creer"), {"modele": "pppt"}).status_code == 403

import datetime

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction

from copro.models import Batiment, CleRepartition, Detention, Lot, PartieCommune, Personne, Tantieme

pytestmark = pytest.mark.django_db


@pytest.fixture
def batiment():
    return Batiment.objects.create(nom="Bâtiment A")


@pytest.fixture
def lot(batiment):
    return Lot.objects.create(numero="A01", type=Lot.Type.LOGEMENT, batiment=batiment)


def test_tantieme_refuse_de_depasser_la_base_de_la_cle(lot, batiment):
    cle = CleRepartition.objects.create(nom="Générales", base=100)
    Tantieme.objects.create(lot=lot, cle=cle, valeur=60)
    autre = Lot.objects.create(numero="A02", type=Lot.Type.LOGEMENT, batiment=batiment)
    with pytest.raises(ValidationError, match="Dépasse la base"):
        Tantieme(lot=autre, cle=cle, valeur=41).full_clean()
    Tantieme(lot=autre, cle=cle, valeur=40).full_clean()


def test_un_seul_tantieme_par_lot_et_par_cle(lot):
    cle = CleRepartition.objects.create(nom="Générales")
    Tantieme.objects.create(lot=lot, cle=cle, valeur=10)
    with pytest.raises(IntegrityError), transaction.atomic():
        Tantieme.objects.create(lot=lot, cle=cle, valeur=20)


def test_escalier_d_un_autre_batiment_refuse(lot):
    autre = Batiment.objects.create(nom="Bâtiment B")
    escalier_b = PartieCommune.objects.create(
        nom="Escalier B", type=PartieCommune.Type.ESCALIER, batiment=autre
    )
    lot.escalier = escalier_b
    with pytest.raises(ValidationError, match="autre bâtiment"):
        lot.full_clean()


def test_partie_commune_qui_n_est_pas_un_escalier_refusee(lot, batiment):
    ascenseur = PartieCommune.objects.create(
        nom="Ascenseur", type=PartieCommune.Type.ASCENSEUR, batiment=batiment
    )
    lot.escalier = ascenseur
    with pytest.raises(ValidationError, match="type escalier"):
        lot.full_clean()


def test_quote_part_superieure_a_un_refusee_par_la_base(lot):
    personne = Personne.objects.create(nom="Exemple")
    with pytest.raises(IntegrityError), transaction.atomic():
        Detention.objects.create(
            personne=personne,
            lot=lot,
            debut=datetime.date(2020, 1, 1),
            quote_part_numerateur=3,
            quote_part_denominateur=2,
        )


def test_periode_inversee_refusee(lot):
    personne = Personne.objects.create(nom="Exemple")
    detention = Detention(
        personne=personne, lot=lot, debut=datetime.date(2024, 1, 1), fin=datetime.date(2023, 1, 1)
    )
    with pytest.raises(ValidationError, match="précède"):
        detention.full_clean()


def test_detentions_actives_a_une_date(lot):
    ancien = Personne.objects.create(nom="Ancien")
    nouveau = Personne.objects.create(nom="Nouveau")
    Detention.objects.create(
        personne=ancien, lot=lot, debut=datetime.date(2020, 1, 1), fin=datetime.date(2024, 6, 30)
    )
    Detention.objects.create(personne=nouveau, lot=lot, debut=datetime.date(2024, 7, 1))
    assert [d.personne.nom for d in lot.detentions_actives(datetime.date(2024, 6, 30))] == ["Ancien"]
    assert [d.personne.nom for d in lot.detentions_actives(datetime.date(2024, 7, 1))] == ["Nouveau"]


def test_personne_morale_sans_prenom():
    with pytest.raises(ValidationError):
        Personne(type=Personne.Type.MORALE, nom="SCI Démo", prenom="Jean").full_clean()


def test_demo_coherente_et_refusee_sur_base_non_vide():
    call_command("charger_demo")
    assert Lot.objects.count() == 32
    assert {
        t: Lot.objects.filter(type=t).count() for t in Lot.Type.values if Lot.objects.filter(type=t).exists()
    } == {
        Lot.Type.LOGEMENT: 21,
        Lot.Type.CAVE: 5,
        Lot.Type.PARKING: 6,
    }
    for cle in CleRepartition.objects.all():
        assert cle.est_complete(), cle
    for tantieme in Tantieme.objects.all():
        tantieme.full_clean()
    assert CleRepartition.objects.get(nom="Charges générales").tantiemes.count() == 32
    # Le rez-de-chaussée ne paie pas l'ascenseur.
    assert not Tantieme.objects.filter(cle__nom__startswith="Ascenseur", lot__etage=0).exists()
    # Chaque lot a au moins un détenteur en cours ; quote-parts de 1 par lot.
    for lot in Lot.objects.all():
        actives = lot.detentions_actives()
        assert actives.exists(), lot
        assert sum(d.quote_part_numerateur / d.quote_part_denominateur for d in actives) == 1, lot
    assert all(p.email.endswith("@example.org") for p in Personne.objects.all())
    with pytest.raises(CommandError, match="déjà des lots"):
        call_command("charger_demo")


def test_demo_avec_activite():
    from echeances.models import Echeance
    from incidents.models import Incident, Statut

    call_command("charger_demo", "--activite")
    assert Echeance.objects.filter(partie_commune__type=PartieCommune.Type.ASCENSEUR).count() == 3
    assert Echeance.objects.get(titre="Vérification des extincteurs").realisations.count() == 1
    statuts = set(Incident.objects.values_list("statut", flat=True))
    assert {Statut.NOUVEAU, Statut.TRANSMIS, Statut.RESOLU} <= statuts
    for incident in Incident.objects.all():
        incident.full_clean()


def test_pages_admin_des_modeles_s_ouvrent(admin_client, admin_user):
    from allauth.mfa.models import Authenticator

    Authenticator.objects.create(user=admin_user, type=Authenticator.Type.TOTP, data={"secret": "x"})
    call_command("charger_demo")
    for modele in ["batiment", "partiecommune", "lot", "clerepartition", "personne"]:
        assert admin_client.get(f"/admin/copro/{modele}/").status_code == 200
        assert admin_client.get(f"/admin/copro/{modele}/add/").status_code == 200
    lot = Lot.objects.first()
    assert admin_client.get(f"/admin/copro/lot/{lot.pk}/change/").status_code == 200

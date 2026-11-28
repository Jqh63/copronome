"""Eau : consommation entre deux dates, anomalies, relevés en ajout seul,
tournée par bâtiment, export des m³ par lot, droits rôle par rôle."""

import csv
import datetime
import io
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from acces.models import Role
from copro.models import Batiment, Lot, PartieCommune
from eau.models import Compteur, Releve, consommation, historique
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db
postgres = pytest.mark.skipif(connection.vendor != "postgresql", reason="trigger propre à Postgres")
D = datetime.date


@pytest.fixture
def lieux():
    a = Batiment.objects.create(nom="Bâtiment A", ordre=1)
    b = Batiment.objects.create(nom="Bâtiment B", ordre=2)
    return {
        "a": a,
        "b": b,
        "lot_a": Lot.objects.create(numero="101", type=Lot.Type.LOGEMENT, batiment=a),
        "lot_b": Lot.objects.create(numero="201", type=Lot.Type.LOGEMENT, batiment=b),
        "local_b": PartieCommune.objects.create(
            nom="Local poubelles", type=PartieCommune.Type.LOCAL, batiment=b
        ),
    }


def _releve(compteur, date, index, **kwargs):
    return Releve.objects.create(compteur=compteur, releve_le=date, index=Decimal(str(index)), **kwargs)


# --- Calculs ------------------------------------------------------------------


def test_consommation_entre_deux_releves(lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    _releve(c, D(2024, 10, 30), 240)
    _releve(c, D(2025, 4, 15), 251)
    _releve(c, D(2025, 10, 31), 260)
    m3, debut, fin = consommation(c, D(2024, 10, 31), D(2025, 10, 31))
    assert (m3, debut.index, fin.index) == (Decimal("20"), Decimal("240"), Decimal("260"))


def test_compteur_pose_en_cours_de_periode_part_de_son_premier_releve(lieux):
    ancien = Compteur.objects.create(numero="E1", lot=lieux["lot_b"], actif=False)
    _releve(ancien, D(2024, 10, 31), 100)
    _releve(ancien, D(2025, 3, 1), 108)  # relevé de dépose
    neuf = Compteur.objects.create(numero="E2", lot=lieux["lot_b"])
    _releve(neuf, D(2025, 3, 1), 0)  # index de pose
    _releve(neuf, D(2025, 10, 31), 12)
    periode = (D(2024, 10, 31), D(2025, 10, 31))
    assert consommation(ancien, *periode)[0] == Decimal("8")
    assert consommation(neuf, *periode)[0] == Decimal("12")


def test_releve_manquant_ne_devine_rien(lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    _releve(c, D(2025, 10, 31), 260)
    m3, debut, fin = consommation(c, D(2024, 10, 31), D(2025, 10, 31))
    assert m3 is None and debut == fin


def test_releve_corrige_sort_des_calculs(lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    _releve(c, D(2024, 10, 31), 240)
    faux = _releve(c, D(2025, 10, 31), 620)  # 260 mal lu
    _releve(c, D(2025, 10, 31), 260, corrige=faux)
    assert consommation(c, D(2024, 10, 31), D(2025, 10, 31))[0] == Decimal("20")
    assert [ligne["releve"].index for ligne in historique(c)] == [Decimal("240"), Decimal("260")]


def test_correction_d_un_autre_compteur_refusee(lieux):
    c1 = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    c2 = Compteur.objects.create(numero="E2", lot=lieux["lot_a"])
    releve = _releve(c1, D(2025, 1, 1), 10)
    with pytest.raises(ValidationError):
        _releve(c2, D(2025, 1, 2), 11, corrige=releve)


def test_index_en_baisse_signale(lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    _releve(c, D(2025, 1, 1), 250, source=Releve.Source.CS)
    _releve(c, D(2025, 2, 1), 245, source=Releve.Source.SYNDIC)
    assert [ligne["baisse"] for ligne in historique(c)] == [False, True]


def test_compteur_lot_ou_partie_commune_exclusivement(lieux):
    with pytest.raises(ValidationError):
        Compteur(numero="X", lot=lieux["lot_b"], partie_commune=lieux["local_b"]).full_clean()
    with pytest.raises(ValidationError):
        Compteur(numero="Y").full_clean()


# --- Ajout seul ---------------------------------------------------------------


def test_releve_en_ajout_seul_par_l_orm(lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    releve = _releve(c, D(2025, 1, 1), 10)
    releve.index = Decimal("11")
    with pytest.raises(ValidationError):
        releve.save()
    with pytest.raises(ValidationError):
        releve.delete()
    with pytest.raises(ValidationError):
        Releve.objects.update(index=0)
    with pytest.raises(ValidationError):
        Releve.objects.all().delete()


@postgres
@pytest.mark.parametrize(
    "requete", ["UPDATE eau_releve SET id = id", "DELETE FROM eau_releve", "TRUNCATE eau_releve CASCADE"]
)
def test_postgres_refuse_update_delete_truncate(lieux, requete):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    _releve(c, D(2025, 1, 1), 10)
    with connection.cursor() as curseur:
        curseur.execute("SELECT count(*) FROM eau_releve")
        assert curseur.fetchone()[0] > 0  # contrôle positif : le trigger de ligne a une ligne à refuser
        curseur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(DatabaseError, match="ajout seul"):
            with transaction.atomic():
                curseur.execute(requete)


# --- Vues ---------------------------------------------------------------------


def test_tournee_enregistre_les_index_saisis_seulement(client, lieux):
    c1 = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    c2 = Compteur.objects.create(numero="E2", partie_commune=lieux["local_b"])
    Compteur.objects.create(numero="E3", lot=lieux["lot_a"])  # autre bâtiment : absent du formulaire
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    url = reverse("eau:tournee", args=[lieux["b"].pk])
    page = client.get(url)
    assert b"E1" in page.content and b"E2" in page.content and b"E3" not in page.content
    reponse = client.post(
        url, {"releve_le": "2025-10-31", "source": "cs", f"index_{c1.pk}": "260.5", f"index_{c2.pk}": ""}
    )
    assert reponse.status_code == 302
    releve = Releve.objects.get()
    assert (releve.compteur, releve.index, releve.auteur.email) == (c1, Decimal("260.5"), "cs@example.org")


def test_tournee_refuse_index_negatif_et_date_future(client, lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    url = reverse("eau:tournee", args=[lieux["b"].pk])
    assert (
        client.post(url, {"releve_le": "2025-10-31", "source": "cs", f"index_{c.pk}": "-1"}).status_code
        == 400
    )
    assert (
        client.post(url, {"releve_le": "2999-01-01", "source": "cs", f"index_{c.pk}": "1"}).status_code == 400
    )
    assert client.post(url, {"releve_le": "2025-10-31", "source": "cs"}).status_code == 400  # rien saisi
    assert not Releve.objects.exists()


def test_correction_par_la_page_du_compteur(client, lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    faux = _releve(c, D(2025, 10, 31), 620)
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    reponse = client.post(
        reverse("eau:ajouter_releve", args=[c.pk]),
        {"releve_le": "2025-10-31", "index": "260", "source": "cs", "corrige": faux.pk},
    )
    assert reponse.status_code == 302
    assert Releve.objects.get(corrige=faux).index == Decimal("260")
    # un relevé déjà corrigé ne se corrige pas deux fois
    reponse = client.post(
        reverse("eau:ajouter_releve", args=[c.pk]),
        {"releve_le": "2025-10-31", "index": "261", "source": "cs", "corrige": faux.pk},
    )
    assert reponse.status_code == 404


def test_export_m3_par_lot_et_cellules_neutralisees(client, lieux):
    lot = Lot.objects.create(numero="=1+1", type=Lot.Type.CAVE, batiment=lieux["b"])
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    _releve(c, D(2024, 10, 31), 240)
    _releve(c, D(2025, 10, 31), 260)
    piege = Compteur.objects.create(numero="E9", lot=lot)
    _releve(piege, D(2025, 10, 31), 5)
    client.force_login(_compte("controle@example.org", Role.CONTROLEUR))
    reponse = client.get(reverse("eau:exporter"), {"debut": "2024-10-31", "fin": "2025-10-31"})
    assert reponse.status_code == 200
    lignes = list(csv.reader(io.StringIO(reponse.content.decode("utf-8-sig")), delimiter=";"))
    assert lignes[0][-1] == "m3"
    par_compteur = {ligne[2]: ligne for ligne in lignes[1:]}
    assert par_compteur["E1"][0] == "201" and par_compteur["E1"][-1] == "20.000"
    assert par_compteur["E9"][0] == "'=1+1" and par_compteur["E9"][-1] == "relevé manquant"


def test_export_periode_invalide(client, lieux):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    assert (
        client.get(reverse("eau:exporter"), {"debut": "2025-10-31", "fin": "2024-10-31"}).status_code == 400
    )


def test_deposer_sort_le_compteur_de_la_tournee(client, lieux):
    c = Compteur.objects.create(numero="E1", lot=lieux["lot_b"])
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    assert client.post(reverse("eau:deposer", args=[c.pk])).status_code == 302
    c.refresh_from_db()
    assert not c.actif
    assert b"E1" not in client.get(reverse("eau:tournee", args=[lieux["b"].pk])).content


# --- Droits -------------------------------------------------------------------

ATTENDU = {  # rôle -> (liste, tournée)
    Role.ADMIN: (200, 403),
    Role.PRESIDENT: (200, 200),
    Role.MEMBRE_CS: (200, 200),
    Role.CONTROLEUR: (200, 403),
    Role.SYNDIC: (403, 403),
    Role.COPROPRIETAIRE: (403, 403),
}


@pytest.mark.parametrize("role", list(ATTENDU))
def test_droits_par_role(client, lieux, role):
    client.force_login(_compte(f"{role}@example.org", role))
    liste = client.get(reverse("eau:liste")).status_code
    tournee = client.get(reverse("eau:tournee", args=[lieux["b"].pk])).status_code
    assert (liste, tournee) == ATTENDU[role]


def test_perimetre_de_batiment(client, lieux):
    c_a = Compteur.objects.create(numero="EA", lot=lieux["lot_a"])
    c_b = Compteur.objects.create(numero="EB", lot=lieux["lot_b"])
    client.force_login(_compte("cs-b@example.org", Role.MEMBRE_CS, batiment=lieux["b"]))
    assert client.get(reverse("eau:compteur", args=[c_b.pk])).status_code == 200
    assert client.get(reverse("eau:compteur", args=[c_a.pk])).status_code == 403
    assert client.get(reverse("eau:tournee", args=[lieux["a"].pk])).status_code == 403
    assert client.post(reverse("eau:deposer", args=[c_a.pk])).status_code == 403
    page = client.get(reverse("eau:liste")).content
    assert b"EB" in page and b"EA" not in page
    reponse = client.get(reverse("eau:exporter"), {"debut": "2024-10-31", "fin": "2025-10-31"})
    assert b"EA" not in reponse.content

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from acces.models import Affectation, Role
from audit.models import Action, JournalAudit
from copro.models import Batiment, Detention, Lot, Occupation, Personne
from copro.purge import DUREE_ANS, purger

pytestmark = pytest.mark.django_db

AUJOURDHUI = datetime.date(2030, 6, 15)
IL_Y_A_6_ANS = datetime.date(2024, 6, 14)
IL_Y_A_4_ANS = datetime.date(2026, 6, 14)


@pytest.fixture
def lot():
    batiment = Batiment.objects.create(nom="Bâtiment A")
    return Lot.objects.create(numero="A01", type=Lot.Type.LOGEMENT, batiment=batiment)


def personne(nom):
    return Personne.objects.create(
        nom=nom, prenom="Camille", email=f"{nom.lower()}@example.org", telephone="00 00 00 00 00"
    )


def vendu_le(p, lot, fin):
    Detention.objects.create(personne=p, lot=lot, debut=datetime.date(2010, 1, 1), fin=fin)


def test_duree_de_cinq_ans():
    assert DUREE_ANS == 5


def test_ancien_proprietaire_efface_apres_cinq_ans(lot):
    p = personne("Vendeur")
    vendu_le(p, lot, IL_Y_A_6_ANS)
    purger(AUJOURDHUI, appliquer=True)
    p.refresh_from_db()
    assert p.efface_le == AUJOURDHUI
    assert (p.nom, p.prenom, p.email, p.telephone) == ("Personne effacée", "", "", "")
    # L'historique du lot garde ses dates.
    assert Detention.objects.get(personne=p).fin == IL_Y_A_6_ANS


def test_garde_avant_cinq_ans(lot):
    p = personne("Recent")
    vendu_le(p, lot, IL_Y_A_4_ANS)
    purger(AUJOURDHUI, appliquer=True)
    p.refresh_from_db()
    assert p.efface_le is None and p.nom == "Recent"


def test_garde_qui_detient_encore_un_autre_lot(lot):
    p = personne("Toujours")
    vendu_le(p, lot, IL_Y_A_6_ANS)
    autre = Lot.objects.create(numero="A02", type=Lot.Type.CAVE, batiment=lot.batiment)
    Detention.objects.create(personne=p, lot=autre, debut=datetime.date(2010, 1, 1))
    purger(AUJOURDHUI, appliquer=True)
    p.refresh_from_db()
    assert p.efface_le is None


def test_ancien_locataire_efface(lot):
    p = personne("Locataire")
    Occupation.objects.create(personne=p, lot=lot, debut=datetime.date(2015, 1, 1), fin=IL_Y_A_6_ANS)
    purger(AUJOURDHUI, appliquer=True)
    p.refresh_from_db()
    assert p.efface_le == AUJOURDHUI


def test_personne_sans_aucun_lien_gardee():
    p = personne("Saisie")
    purger(AUJOURDHUI, appliquer=True)
    p.refresh_from_db()
    assert p.efface_le is None


def test_compte_actif_bloque_la_purge(lot):
    p = personne("Membre")
    vendu_le(p, lot, IL_Y_A_6_ANS)
    compte = get_user_model().objects.create_user(
        username="m@example.org", email="m@example.org", password="x"
    )
    Affectation.objects.create(utilisateur=compte, role=Role.MEMBRE_CS, personne=p)
    a_effacer, bloquees = purger(AUJOURDHUI, appliquer=True)
    p.refresh_from_db()
    assert p.efface_le is None and [b[0] for b in bloquees] == [p] and a_effacer == []
    compte.is_active = False
    compte.save()
    purger(AUJOURDHUI, appliquer=True)
    p.refresh_from_db()
    assert p.efface_le == AUJOURDHUI


def test_decompte_seul_sans_appliquer(lot):
    p = personne("Vendeur")
    vendu_le(p, lot, IL_Y_A_6_ANS)
    a_effacer, _ = purger(AUJOURDHUI)
    p.refresh_from_db()
    assert len(a_effacer) == 1 and p.efface_le is None


def test_journal_sans_le_nom_efface_et_purge_idempotente(lot):
    p = personne("Dupont")
    vendu_le(p, lot, IL_Y_A_6_ANS)
    purger(AUJOURDHUI, appliquer=True)
    purger(AUJOURDHUI, appliquer=True)
    entrees = JournalAudit.objects.filter(action=Action.PERSONNE_EFFACEE)
    assert entrees.count() == 1
    entree = entrees.get()
    assert "Dupont" not in f"{entree.objet_libelle} {entree.detail}"
    assert entree.detail == {"fin_du_dernier_lien": IL_Y_A_6_ANS.isoformat(), "duree_ans": 5}


def test_commande_n_affiche_aucun_nom(lot, capsys):
    p = personne("Dupont")
    vendu_le(p, lot, datetime.date(2011, 1, 1))
    call_command("purger_anciens")
    sortie = capsys.readouterr().out
    assert "1 personne(s) à effacer" in sortie and "Dupont" not in sortie
    p.refresh_from_db()
    assert p.efface_le is None
    call_command("purger_anciens", "--appliquer")
    assert "1 personne(s) effacée(s)" in capsys.readouterr().out

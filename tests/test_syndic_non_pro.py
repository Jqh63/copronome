"""Rôle « syndic non professionnel » (ADR domaine et instances, § 7) : pouvoirs
de gestion, distinct du président du CS ; en coopératif, le président cumule."""

import pytest

from acces.droits import DOMAINES, ECRIRE, LIRE, peut
from acces.models import ROLES_MFA_OBLIGATOIRE, Affectation, Role
from documents.models import Visibilite
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db


class _Doc:
    batiment_id = None

    def __init__(self, visibilite):
        self.visibilite = visibilite


def test_gere_tous_les_domaines_metier_et_les_comptes():
    syndic = _compte("syndic-np@example.org", Role.SYNDIC_NON_PRO)
    for domaine in DOMAINES - {"audit"}:
        assert peut(syndic, ECRIRE, domaine), domaine
    assert peut(syndic, LIRE, "audit") and not peut(syndic, ECRIRE, "audit")


def test_second_facteur_obligatoire():
    assert Role.SYNDIC_NON_PRO in ROLES_MFA_OBLIGATOIRE


def test_documents_du_cs_reserves_sauf_cumul_cooperatif():
    syndic = _compte("syndic-np@example.org", Role.SYNDIC_NON_PRO)
    assert not peut(syndic, LIRE, "documents", _Doc(Visibilite.CS))
    assert peut(syndic, LIRE, "documents", _Doc(Visibilite.COMPTES))
    # Coopératif : le président du CS exerce les fonctions de syndic.
    Affectation.objects.create(utilisateur=syndic, role=Role.PRESIDENT)
    syndic = type(syndic).objects.get(pk=syndic.pk)
    assert peut(syndic, LIRE, "documents", _Doc(Visibilite.CS))


def test_le_syndic_professionnel_reste_sans_droit_de_saisie():
    pro = _compte("syndic-pro@example.org", Role.SYNDIC)
    for domaine in DOMAINES:
        assert not peut(pro, ECRIRE, domaine), domaine

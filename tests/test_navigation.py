"""Menu principal : une entrée est visible si et seulement si sa vue répond 200."""

import pytest
from django.core.management import call_command
from django.urls import reverse

from acces.models import Role
from copronome.navigation import ENTREES, entrees_visibles
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db


@pytest.fixture
def demo():
    call_command("charger_demo")


@pytest.mark.parametrize("role", list(Role))
def test_menu_egal_aux_vues_accessibles(client, demo, role):
    utilisateur = _compte(f"{role}@example.org", role)
    client.force_login(utilisateur)
    affichees = {entree["url"] for entree in entrees_visibles(utilisateur)}
    for _, nom in ENTREES:
        url = reverse(nom)
        assert (url in affichees) == (client.get(url).status_code == 200), (role, url)


def test_page_rend_le_menu_du_role(client, demo):
    client.force_login(_compte("controleur@example.org", Role.CONTROLEUR))
    page = client.get(reverse("documents:liste")).content.decode()
    assert 'href="/documents/" aria-current="page"' in page
    assert 'href="/incidents/"' not in page
    assert "Se déconnecter" in page


def test_anonyme_sans_menu(client):
    page = client.get(reverse("accueil")).content.decode()
    assert "Se connecter" in page and "Menu principal" not in page

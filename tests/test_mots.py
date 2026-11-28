"""Glossaire et libellés en français courant (revue de l'ADR du 2026-11-27)."""

import pytest
from django.urls import reverse

from acces.models import Role
from tests.test_acces import _compte


@pytest.mark.django_db
def test_glossaire_public_et_lie_depuis_chaque_page(client):
    page = client.get(reverse("mots")).content.decode()
    for ancre in ("lot", "tantiemes", "cle", "syndic", "cs", "controleur", "ag", "index"):
        assert f'id="{ancre}"' in page
    assert reverse("mots") in client.get(reverse("accueil")).content.decode()


@pytest.mark.django_db
def test_pas_de_jargon_en_tete_des_lots(client):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    page = client.get(reverse("lots")).content.decode()
    assert "<th>Tantièmes</th>" not in page
    assert f"{reverse('mots')}#tantiemes" in page

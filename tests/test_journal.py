import io
import logging

import pytest

from copronome.journal import masquer

JETON = "JETONSECRET0123456789"


@pytest.mark.parametrize(
    "chemin",
    [
        f"/agenda/ical/{JETON}/",
        f"/invitation/{JETON}/",
        f"/compte/password/reset/key/1-{JETON}/",
        f"/compte/confirm-email/{JETON}/",
    ],
)
def test_masquer_retire_le_jeton(chemin):
    resultat = masquer(f"Not Found: {chemin}")
    assert JETON not in resultat
    assert "[jeton]" in resultat


def test_masquer_laisse_les_autres_chemins():
    assert masquer("Not Found: /incidents/42/") == "Not Found: /incidents/42/"


@pytest.mark.django_db
def test_un_404_sur_un_jeton_n_ecrit_pas_le_jeton(client):
    # Bout en bout : handler console tel que configuré par LOGGING.
    handler = next(h for h in logging.getLogger().handlers if h.get_name() == "console")
    sortie = io.StringIO()
    ancien = handler.setStream(sortie)
    try:
        assert client.get(f"/agenda/ical/{JETON}/").status_code == 404
    finally:
        handler.setStream(ancien)
    assert JETON not in sortie.getvalue()
    assert "/agenda/ical/[jeton]" in sortie.getvalue()

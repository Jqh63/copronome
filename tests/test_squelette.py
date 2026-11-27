import subprocess
import sys
from pathlib import Path

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_accueil_repond_avec_les_en_tetes_de_securite(client):
    reponse = client.get(reverse("accueil"))
    assert reponse.status_code == 200
    assert "script-src 'self'" in reponse["Content-Security-Policy"]
    assert "unsafe-inline" not in reponse["Content-Security-Policy"]
    assert reponse["X-Frame-Options"] == "DENY"
    assert reponse["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db
def test_sante_interroge_la_base(client):
    reponse = client.get(reverse("sante"))
    assert reponse.status_code == 200
    assert reponse.json() == {"etat": "ok"}


def test_production_refuse_de_demarrer_sans_cle_secrete(tmp_path):
    env = {"COPRONOME_DEBUG": "0", "DJANGO_SETTINGS_MODULE": "copronome.settings", "PATH": ""}
    resultat = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert resultat.returncode != 0
    assert "COPRONOME_SECRET_KEY est obligatoire" in resultat.stderr

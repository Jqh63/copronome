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


def test_collectstatic_du_build_produit_des_noms_haches_et_compresses(tmp_path):
    # Même commande que le Dockerfile, réglages de production : l'app sert
    # ensuite ces fichiers elle-même (WhiteNoise), cache long sur le nom haché.
    env = {
        "COPRONOME_DEBUG": "0",
        "COPRONOME_SECRET_KEY": "test-seulement",
        "COPRONOME_ALLOWED_HOSTS": "build.invalid",
        "COPRONOME_STATIC_ROOT": str(tmp_path),
        "DJANGO_SETTINGS_MODULE": "copronome.settings",
        "PATH": "",
    }
    resultat = subprocess.run(  # noqa: S603
        [sys.executable, "manage.py", "collectstatic", "--noinput", "--verbosity", "0"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert resultat.returncode == 0, resultat.stderr
    assert (tmp_path / "staticfiles.json").is_file()
    haches = list(tmp_path.glob("copronome.*.css"))
    assert [f.name for f in haches if f.name.count(".") == 2], "contrôle positif : nom haché présent"
    assert list(tmp_path.glob("copronome.*.css.gz"))

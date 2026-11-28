"""Réglages d'une instance branchée sous un domaine partagé (ADR domaine et
instances, § 3) : hôtes dérivés de l'URL publique, aucun joker, cookies
__Host-. Chaque cas relance settings.py dans un processus neuf."""

import json
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LIRE = (
    "import json; from django.conf import settings as s; print(json.dumps({k: getattr(s, k) for k in "
    "['ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'SESSION_COOKIE_NAME', 'CSRF_COOKIE_NAME', "
    "'SESSION_COOKIE_DOMAIN', 'SESSION_COOKIE_SECURE', 'INSTANCE_ID']}))"
)


def _reglages(**variables):
    env = {k: v for k, v in os.environ.items() if not k.startswith("COPRONOME_")}
    env |= {"DJANGO_SETTINGS_MODULE": "copronome.settings", "COPRONOME_SECRET_KEY": "x" * 50}
    env |= {f"COPRONOME_{k}": v for k, v in variables.items()}
    code = f"import django; django.setup(); {LIRE}"
    sortie = subprocess.run(  # noqa: S603 — interpréteur courant, code fixe du banc
        [sys.executable, "-c", code], cwd=RACINE, env=env, capture_output=True, text=True, check=False
    )
    return sortie.returncode, (json.loads(sortie.stdout) if sortie.returncode == 0 else sortie.stderr)


def test_hotes_et_origines_derives_de_l_url_publique():
    code, r = _reglages(URL_PUBLIQUE="https://les-tilleuls-exempleville.copronome.example", INSTANCE_ID="i42")
    assert code == 0, r
    assert r["ALLOWED_HOSTS"] == ["les-tilleuls-exempleville.copronome.example"]
    assert r["CSRF_TRUSTED_ORIGINS"] == ["https://les-tilleuls-exempleville.copronome.example"]
    assert r["INSTANCE_ID"] == "i42"


def test_cookies_prefixes_host_sans_domaine():
    code, r = _reglages(ALLOWED_HOSTS="copro.example.org")
    assert code == 0, r
    assert r["SESSION_COOKIE_NAME"].startswith("__Host-") and r["CSRF_COOKIE_NAME"].startswith("__Host-")
    assert r["SESSION_COOKIE_DOMAIN"] is None and r["SESSION_COOKIE_SECURE"] is True


def test_joker_refuse_hors_debug():
    for hotes in (".copronome.example", "*"):
        code, erreur = _reglages(ALLOWED_HOSTS=hotes)
        assert code != 0 and "sans joker" in erreur
    code, erreur = _reglages(ALLOWED_HOSTS="a.example.org", CSRF_TRUSTED_ORIGINS="https://*.example.org")
    assert code != 0 and "sans joker" in erreur

"""Choix du transport des mails selon l'environnement (copronome.settings)."""

import os
import subprocess
import sys

import pytest

CONSOLE = "django.core.mail.backends.console.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"


def transport(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("COPRONOME_")}
    env.update(COPRONOME_SECRET_KEY="essai", COPRONOME_ALLOWED_HOSTS="essai.invalid", **extra)
    code = "from django.conf import settings; print(settings.EMAIL_BACKEND)"
    sortie = subprocess.run(  # noqa: S603
        [sys.executable, "-c", f"import django; django.setup(); {code}"],
        env={**env, "DJANGO_SETTINGS_MODULE": "copronome.settings"},
        capture_output=True,
        text=True,
        check=True,
    )
    return sortie.stdout.strip()


@pytest.mark.parametrize(
    ("extra", "attendu"),
    [
        ({}, SMTP),
        ({"COPRONOME_EMAIL_CONSOLE": "1"}, CONSOLE),
        ({"COPRONOME_EMAIL_CONSOLE": "0"}, SMTP),
        ({"COPRONOME_DEBUG": "1"}, CONSOLE),
    ],
)
def test_transport_des_mails(extra, attendu):
    assert transport(**extra) == attendu

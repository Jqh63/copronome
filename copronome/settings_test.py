"""Réglages des tests : mode debug, SQLite sauf si la CI fournit Postgres."""

import os

os.environ.setdefault("COPRONOME_DEBUG", "1")

from copronome.settings import *  # noqa: E402, F403

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # tests rapides seulement
# Sans manifeste : les tests ne lancent pas collectstatic.
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}  # noqa: F405

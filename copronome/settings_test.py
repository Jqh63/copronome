"""Réglages des tests : mode debug, SQLite sauf si la CI fournit Postgres."""

import os

os.environ.setdefault("COPRONOME_DEBUG", "1")

from copronome.settings import *  # noqa: E402, F403

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # tests rapides seulement

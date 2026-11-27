"""Réglages des tests : mode debug, SQLite sauf si la CI fournit Postgres."""

import os

os.environ.setdefault("COPRONOME_DEBUG", "1")

from copronome.settings import *  # noqa: E402, F403

"""Filtre de journalisation : masque les jetons portés par les URL.

Les URL d'iCal, d'invitation, de réinitialisation et de confirmation portent
un jeton qui vaut accès. Django écrit le chemin des 404 et des 500
(`django.request`) : sans ce filtre, le jeton atterrirait dans le journal.
Même liste de préfixes que le filtre du journal d'accès de docker/Caddyfile.
"""

import logging
import re

PREFIXES_A_JETON = ("agenda/ical", "invitation", "compte/password/reset/key", "compte/confirm-email")
_MOTIF = re.compile(r"/(" + "|".join(re.escape(p) for p in PREFIXES_A_JETON) + r")/[^\s?\"']*")


def masquer(texte):
    return _MOTIF.sub(r"/\1/[jeton]", texte)


class MasqueJetons(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        masque = masquer(message)
        if masque != message:
            record.msg, record.args = masque, None
        return True

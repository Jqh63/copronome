"""Écriture minimale d'un calendrier iCalendar (RFC 5545) : échappement du
texte (§ 3.3.11), lignes pliées à 75 octets (§ 3.1), fins de ligne CRLF."""

import datetime

from django.utils import timezone


def _texte(valeur):
    return (
        str(valeur).replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,").replace("\r\n", "\\n")
    ).replace("\n", "\\n")


def _plier(ligne):
    octets = ligne.encode()
    if len(octets) <= 75:
        return ligne
    morceaux, debut, limite = [], 0, 75
    while debut < len(octets):
        fin = min(debut + limite, len(octets))
        while fin < len(octets) and (octets[fin] & 0xC0) == 0x80:  # ne pas couper un caractère UTF-8
            fin -= 1
        morceaux.append(octets[debut:fin].decode())
        debut, limite = fin, 74  # les lignes de suite commencent par une espace
    return "\r\n ".join(morceaux)


def _utc(moment):
    return moment.astimezone(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def calendrier(nom, evenements):
    """`evenements` : dicts avec uid, titre, debut (datetime ou date), et en
    option fin, lieu, description, annule."""
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Copronome//Agenda//FR",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_texte(nom)}",
    ]
    horodatage = _utc(timezone.now())
    for e in evenements:
        lignes += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{horodatage}"]
        if isinstance(e["debut"], datetime.datetime):
            lignes.append(f"DTSTART:{_utc(e['debut'])}")
            if e.get("fin"):
                lignes.append(f"DTEND:{_utc(e['fin'])}")
        else:
            lignes.append(f"DTSTART;VALUE=DATE:{e['debut']:%Y%m%d}")
            lignes.append(f"DTEND;VALUE=DATE:{e['debut'] + datetime.timedelta(days=1):%Y%m%d}")
        lignes.append(f"SUMMARY:{_texte(e['titre'])}")
        if e.get("lieu"):
            lignes.append(f"LOCATION:{_texte(e['lieu'])}")
        if e.get("description"):
            lignes.append(f"DESCRIPTION:{_texte(e['description'])}")
        if e.get("annule"):
            lignes.append("STATUS:CANCELLED")
        lignes.append("END:VEVENT")
    lignes.append("END:VCALENDAR")
    return "".join(_plier(ligne) + "\r\n" for ligne in lignes)

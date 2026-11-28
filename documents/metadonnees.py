"""Retrait des métadonnées des photos déposées (revue de l'ADR du 2026-11-27).

Une photo de téléphone porte souvent la position GPS du domicile, le modèle de
l'appareil et la date exacte : rien de cela ne doit partir vers les autres
copropriétaires. Le retrait se fait sur la STRUCTURE du fichier (segments JPEG,
blocs PNG), sans décoder l'image : aucune bibliothèque d'image, et aucune bombe
de décompression possible côté serveur.

JPEG : APP1 (EXIF, XMP), APP13 (IPTC) et commentaires retirés ; seule
l'orientation est réécrite dans un EXIF minimal, sinon la photo s'afficherait
tournée. PNG : blocs eXIf, tEXt, zTXt, iTXt et tIME retirés.
"""

import struct

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

ILLISIBLE = "Image illisible ou abîmée."

# Segments JPEG retirés : APP1 (EXIF, XMP), APP13 (IPTC/Photoshop), COM.
_JPEG_RETIRES = {0xE1, 0xED, 0xFE}
# Marqueurs sans longueur (RSTn, TEM).
_JPEG_SANS_LONGUEUR = set(range(0xD0, 0xD8)) | {0x01}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_RETIRES = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}


def _orientation(exif):
    """Valeur 2 à 8 de la balise Orientation (0x0112) de l'IFD0, sinon None."""
    if not exif.startswith(b"Exif\0\0") or len(exif) < 14:
        return None
    tiff = exif[6:]
    ordre = {b"II": "<", b"MM": ">"}.get(tiff[:2])
    if ordre is None:
        return None
    try:
        (ifd,) = struct.unpack_from(ordre + "I", tiff, 4)
        (nombre,) = struct.unpack_from(ordre + "H", tiff, ifd)
        for i in range(nombre):
            balise, type_, _, valeur = struct.unpack_from(ordre + "HHI2s", tiff, ifd + 2 + 12 * i)
            if balise == 0x0112 and type_ == 3:
                (o,) = struct.unpack(ordre + "H", valeur)
                return o if 2 <= o <= 8 else None
    except struct.error:
        return None
    return None


def _exif_minimal(orientation):
    tiff = b"MM\0*" + struct.pack(">I", 8) + struct.pack(">HHHIHH", 1, 0x0112, 3, 1, orientation, 0)
    tiff += struct.pack(">I", 0)  # pas d'IFD suivant
    charge = b"Exif\0\0" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(charge) + 2) + charge


def nettoyer_jpeg(donnees):
    if not donnees.startswith(b"\xff\xd8"):
        raise ValidationError(ILLISIBLE)
    sortie, i, orientation = [b"\xff\xd8"], 2, None
    while True:
        if i + 4 > len(donnees) or donnees[i] != 0xFF:
            raise ValidationError(ILLISIBLE)
        marqueur = donnees[i + 1]
        if marqueur == 0xFF:  # octet de bourrage
            i += 1
            continue
        if marqueur in _JPEG_SANS_LONGUEUR:
            sortie.append(donnees[i : i + 2])
            i += 2
            continue
        (longueur,) = struct.unpack_from(">H", donnees, i + 2)
        fin = i + 2 + longueur
        if longueur < 2 or fin > len(donnees):
            raise ValidationError(ILLISIBLE)
        segment = donnees[i:fin]
        if marqueur == 0xDA:  # début des données : la suite est recopiée telle quelle
            if orientation:
                sortie.insert(1, _exif_minimal(orientation))
            sortie.append(donnees[i:])
            return b"".join(sortie)
        if marqueur == 0xE1:
            orientation = orientation or _orientation(segment[4:])
        if marqueur not in _JPEG_RETIRES:
            sortie.append(segment)
        i = fin


def nettoyer_png(donnees):
    if not donnees.startswith(_PNG_SIGNATURE):
        raise ValidationError(ILLISIBLE)
    sortie, i = [_PNG_SIGNATURE], len(_PNG_SIGNATURE)
    while i < len(donnees):
        if i + 12 > len(donnees):
            raise ValidationError(ILLISIBLE)
        (longueur,) = struct.unpack_from(">I", donnees, i)
        type_ = donnees[i + 4 : i + 8]
        fin = i + 12 + longueur
        if fin > len(donnees):
            raise ValidationError(ILLISIBLE)
        if type_ not in _PNG_RETIRES:
            sortie.append(donnees[i:fin])
        i = fin
        if type_ == b"IEND":
            return b"".join(sortie)
    raise ValidationError(ILLISIBLE)


_NETTOYEURS = {"image/jpeg": nettoyer_jpeg, "image/png": nettoyer_png}


def sans_metadonnees(fichier, type_mime):
    """Fichier à enregistrer : copie nettoyée pour une photo, l'original sinon."""
    nettoyeur = _NETTOYEURS.get(type_mime)
    if nettoyeur is None:
        return fichier
    fichier.seek(0)
    propre = ContentFile(nettoyeur(fichier.read()), name=fichier.name)
    fichier.seek(0)
    return propre

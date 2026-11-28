"""Retrait des métadonnées des photos (documents/metadonnees.py) et lecture
bornée de l'entrée `mimetype` des fichiers OpenDocument.

Les fixtures sont de vraies images écrites par Pillow 12.2 (le 2026-11-28) :
GPS 45°46'30"N 3°5'10"E, fabricant, orientation 6, XMP avec GPS, commentaire
(JPEG) ; texte, XMP et eXIf (PNG). Vérifié ce jour-là avec Pillow, hors banc :
images nettoyées décodées, pixels identiques, EXIF réduit à {Orientation: 6}."""

import io
import struct
import zipfile
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from acces.models import Role
from documents.metadonnees import _orientation, nettoyer_jpeg, nettoyer_png
from documents.models import Categorie, Document, Visibilite
from documents.validation import detecter_type
from tests.test_acces import _compte

FIXTURES = Path(__file__).parent / "fixtures"
JPEG = (FIXTURES / "photo-gps.jpg").read_bytes()
PNG_GPS = (FIXTURES / "photo-gps.png").read_bytes()
SECRETS = (b"GPSLatitude", b"Fabricant", b"secret", b"xmpmeta")


def _segments_jpeg(donnees):
    """(marqueur, contenu) jusqu'au début des données, puis (0xDA, reste)."""
    i, sortie = 2, []
    while True:
        marqueur = donnees[i + 1]
        if marqueur == 0xDA:
            return sortie + [(0xDA, donnees[i:])]
        (longueur,) = struct.unpack_from(">H", donnees, i + 2)
        sortie.append((marqueur, donnees[i + 4 : i + 2 + longueur]))
        i += 2 + longueur


def _blocs_png(donnees):
    i, sortie = 8, []
    while i < len(donnees):
        (longueur,) = struct.unpack_from(">I", donnees, i)
        sortie.append((donnees[i + 4 : i + 8], donnees[i + 8 : i + 8 + longueur]))
        i += 12 + longueur
    return sortie


def test_fixtures_portent_bien_les_metadonnees():
    """Contrôle positif : sans lui, « secret absent » ne prouverait rien."""
    assert all(s in JPEG for s in SECRETS)
    assert b"secret" in PNG_GPS and b"eXIf" in PNG_GPS


def test_jpeg_sans_gps_ni_xmp_ni_commentaire_orientation_gardee():
    propre = nettoyer_jpeg(JPEG)
    assert not any(s in propre for s in SECRETS)
    avant, apres = _segments_jpeg(JPEG), _segments_jpeg(propre)
    assert [m for m, _ in apres if m in (0xE1, 0xED, 0xFE)] == [0xE1], "un seul APP1 : l'EXIF minimal"
    exif = next(c for m, c in apres if m == 0xE1)
    assert _orientation(exif) == 6
    assert len(exif) < 40
    # Tables, profil couleur (APP2) et données d'image recopiés à l'identique.
    garder = [(m, c) for m, c in avant if m not in (0xE1, 0xED, 0xFE)]
    assert [(m, c) for m, c in apres if m != 0xE1] == garder
    assert any(m == 0xE2 for m, _ in apres)


def test_jpeg_sans_orientation_pas_d_exif():
    sans = b"\xff\xd8" + b"".join(
        b"\xff" + bytes([m]) + struct.pack(">H", len(c) + 2) + c
        for m, c in _segments_jpeg(JPEG)[:-1]
        if m != 0xE1
    )
    sans += _segments_jpeg(JPEG)[-1][1]
    assert not any(m == 0xE1 for m, _ in _segments_jpeg(nettoyer_jpeg(sans)))


def test_png_sans_texte_ni_exif_image_intacte():
    propre = nettoyer_png(PNG_GPS)
    assert not any(s in propre for s in SECRETS)
    types = [t for t, _ in _blocs_png(propre)]
    assert not {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"} & set(types)
    assert types[0] == b"IHDR" and types[-1] == b"IEND"
    idat = [c for t, c in _blocs_png(PNG_GPS) if t == b"IDAT"]
    assert [c for t, c in _blocs_png(propre) if t == b"IDAT"] == idat


@pytest.mark.parametrize(
    ("nettoyeur", "donnees"),
    [
        (nettoyer_jpeg, JPEG[:40]),
        (nettoyer_jpeg, b"\xff\xd8\xff\xe0\xff\xff"),
        (nettoyer_jpeg, b"\xff\xd8\x00\x00\x00\x00"),
        (nettoyer_png, PNG_GPS[:-12]),
        (nettoyer_png, PNG_GPS[:30]),
    ],
)
def test_image_tronquee_refusee(nettoyeur, donnees):
    with pytest.raises(ValidationError, match="illisible"):
        nettoyeur(donnees)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("nom", "contenu", "type_mime"), [("p.jpg", JPEG, "image/jpeg"), ("p.png", PNG_GPS, "image/png")]
)
def test_photo_deposee_enregistree_sans_metadonnees(client, settings, tmp_path, nom, contenu, type_mime):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    donnees = {"titre": "Fuite", "categorie": Categorie.PHOTO, "visibilite": Visibilite.CS}
    donnees["fichier"] = SimpleUploadedFile(nom, contenu, content_type="application/octet-stream")
    assert client.post(reverse("documents:deposer"), donnees).status_code == 302
    document = Document.objects.get()
    with document.fichier.open("rb") as f:
        enregistre = f.read()
    assert document.type_mime == type_mime
    assert not any(s in enregistre for s in SECRETS)
    assert document.taille == len(enregistre) < len(contenu)
    assert document.nom_origine == nom


def _ods(mimetype):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("content.xml", "<x/>")
    return io.BytesIO(tampon.getvalue())


def test_mimetype_geant_non_lu():
    """Bombe de décompression : une entrée `mimetype` de plusieurs Mo n'est pas
    décompressée (taille déclarée lue avant), le fichier est refusé."""
    bombe = _ods("application/vnd.oasis.opendocument.text" + " " * 5_000_000)
    assert len(bombe.getvalue()) < 50_000
    with pytest.raises(ValidationError):
        detecter_type(bombe)
    assert (
        detecter_type(_ods("application/vnd.oasis.opendocument.text"))
        == "application/vnd.oasis.opendocument.text"
    )

"""Liste blanche des fichiers acceptés, vérifiée sur le CONTENU (ADR, modèle
de menace : fichier piégé). Le nom et le type annoncés par le navigateur sont
ignorés : l'extension enregistrée vient du type détecté ici.

Refusés par construction : HTML, SVG, exécutables, scripts, archives, et les
documents Office à macros (présence de `vbaProject.bin`).
"""

import zipfile

from django.core.exceptions import ValidationError

# type MIME -> extension enregistrée
TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
}

# Fichier principal attendu dans l'archive d'un document Office Open XML.
_OOXML = {
    "word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xl/workbook.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_ODF = {
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
}

REFUS = "Type de fichier non accepté (PDF, PNG, JPEG, Word, Excel ou OpenDocument)."


def _type_archive(fichier):
    try:
        with zipfile.ZipFile(fichier) as archive:
            noms = archive.namelist()
            if any(nom.lower().endswith("vbaproject.bin") for nom in noms):
                raise ValidationError("Document à macros refusé.")
            # ODF : l'entrée `mimetype` vient en premier et porte le type.
            if noms and noms[0] == "mimetype":
                type_odf = archive.read("mimetype").decode("ascii", "replace").strip()
                if type_odf in _ODF:
                    return type_odf
            if "[Content_Types].xml" in noms:
                for principal, type_ooxml in _OOXML.items():
                    if principal in noms:
                        return type_ooxml
    except zipfile.BadZipFile:
        pass
    return None


def detecter_type(fichier):
    """Renvoie le type MIME détecté, ou lève ValidationError."""
    fichier.seek(0)
    tete = fichier.read(8)
    fichier.seek(0)
    if tete.startswith(b"%PDF-"):
        type_mime = "application/pdf"
    elif tete.startswith(b"\x89PNG\r\n\x1a\n"):
        type_mime = "image/png"
    elif tete.startswith(b"\xff\xd8\xff"):
        type_mime = "image/jpeg"
    elif tete.startswith(b"PK\x03\x04"):
        type_mime = _type_archive(fichier)
        fichier.seek(0)
    else:
        type_mime = None
    if type_mime is None:
        raise ValidationError(REFUS)
    return type_mime

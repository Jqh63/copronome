"""Documents : liste blanche sur le contenu, taille, quota, empreinte, service
en pièce jointe, et matrice rôle × visibilité × périmètre."""

import hashlib
import io
import zipfile

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from acces.models import Role
from copro.models import Batiment
from documents.models import Categorie, Document, Visibilite
from documents.validation import detecter_type
from tests.test_acces import _compte

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
# PNG 1×1 valide, sans métadonnées (le nettoyage le laisse intact).
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x00\x00\x00\x00:~\x9bU"
    b"\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _zip(entrees, premiere=None):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        if premiere:
            archive.writestr(*premiere)
        for nom, contenu in entrees.items():
            archive.writestr(nom, contenu)
    return tampon.getvalue()


DOCX = _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": "<w:document/>"})
ODT = _zip({"content.xml": "<office/>"}, premiere=("mimetype", "application/vnd.oasis.opendocument.text"))
DOCM = _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": "<w/>", "word/vbaProject.bin": "x"})


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def demo():
    call_command("charger_demo")


@pytest.mark.parametrize(
    "contenu, attendu",
    [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 16, "image/jpeg"),
        (DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        (ODT, "application/vnd.oasis.opendocument.text"),
    ],
)
def test_types_acceptes_reconnus_sur_le_contenu(contenu, attendu):
    assert detecter_type(io.BytesIO(contenu)) == attendu


@pytest.mark.parametrize(
    "contenu",
    [
        b"<!doctype html><script>alert(1)</script>",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
        b"MZ\x90\x00" + b"\x00" * 16,  # exécutable Windows
        b"#!/bin/sh\nrm -rf /\n",
        _zip({"a.txt": "x"}),  # archive quelconque
        DOCM,  # Word à macros
        b"PK\x03\x04 pas une archive",
        b"",
    ],
)
def test_types_refuses(contenu):
    with pytest.raises(ValidationError):
        detecter_type(io.BytesIO(contenu))


def _deposer(client, contenu, nom="devis.pdf", **champs):
    donnees = {"titre": "Devis toiture", "categorie": Categorie.DEVIS, "visibilite": Visibilite.CS}
    donnees.update(champs)
    donnees["fichier"] = SimpleUploadedFile(nom, contenu, content_type="application/pdf")
    return client.post(reverse("documents:deposer"), donnees)


def test_depot_enregistre_empreinte_taille_et_type_detecte(client, demo):
    membre = _compte("cs@example.org", Role.MEMBRE_CS)
    client.force_login(membre)
    assert _deposer(client, PDF).status_code == 302
    document = Document.objects.get()
    assert document.empreinte == hashlib.sha256(PDF).hexdigest()
    assert document.taille == len(PDF)
    assert document.type_mime == "application/pdf"
    assert document.nom_origine == "devis.pdf"
    assert document.depose_par == membre
    # Nom aléatoire sur disque, extension du type détecté.
    assert document.fichier.name.startswith("documents/") and document.fichier.name.endswith(".pdf")
    assert "devis" not in document.fichier.name


def test_nom_trompeur_ignore_html_deguise_en_pdf_refuse(client, demo):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    reponse = _deposer(client, b"<html><script>x</script></html>", nom="facture.pdf")
    assert reponse.status_code == 400
    assert Document.objects.count() == 0


def test_extension_enregistree_vient_du_contenu(client, demo):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    _deposer(client, PNG, nom="photo.pdf", categorie=Categorie.PHOTO)
    assert Document.objects.get().fichier.name.endswith(".png")


def test_taille_maximale(client, demo, settings):
    settings.DOCUMENT_TAILLE_MAX = len(PDF) - 1
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    reponse = _deposer(client, PDF)
    assert reponse.status_code == 400
    assert "trop gros" in reponse.content.decode()
    assert Document.objects.count() == 0


def test_quota_global(client, demo, settings):
    settings.DOCUMENTS_QUOTA = len(PDF) + 10
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    assert _deposer(client, PDF).status_code == 302
    reponse = _deposer(client, PDF)
    assert reponse.status_code == 400
    assert "quota" in reponse.content.decode()
    assert Document.objects.count() == 1


def test_telechargement_en_piece_jointe(client, demo):
    client.force_login(_compte("cs@example.org", Role.MEMBRE_CS))
    _deposer(client, PDF)
    reponse = client.get(reverse("documents:telecharger", args=[Document.objects.get().pk]))
    assert reponse.status_code == 200
    assert reponse["Content-Disposition"].startswith("attachment;")
    assert reponse["Content-Type"] == "application/pdf"
    assert reponse["X-Content-Type-Options"] == "nosniff"
    assert reponse["Cache-Control"] == "private, no-store"
    assert b"".join(reponse.streaming_content) == PDF


def _document(visibilite, batiment=None):
    return Document.objects.create(
        titre=f"doc {visibilite}",
        categorie=Categorie.AUTRE,
        visibilite=visibilite,
        batiment=batiment,
        fichier=SimpleUploadedFile("x.pdf", PDF),
        nom_origine="x.pdf",
        type_mime="application/pdf",
        taille=len(PDF),
        empreinte=hashlib.sha256(PDF).hexdigest(),
    )


# Lecture d'un document selon sa visibilité, rôle par rôle (ADR, § 4).
ATTENDU_LECTURE = {
    Role.ADMIN: {"cs": 200, "comptes": 200, "tous": 200},
    Role.PRESIDENT: {"cs": 200, "comptes": 200, "tous": 200},
    Role.MEMBRE_CS: {"cs": 200, "comptes": 200, "tous": 200},
    Role.CONTROLEUR: {"cs": 403, "comptes": 200, "tous": 200},
    # Pas encore de droit « lire documents » : rien, même un document « tous ».
    Role.SYNDIC_NON_PRO: {"cs": 403, "comptes": 200, "tous": 200},
    Role.SYNDIC: {"cs": 403, "comptes": 403, "tous": 403},
    Role.COPROPRIETAIRE: {"cs": 403, "comptes": 403, "tous": 403},
}


@pytest.mark.parametrize("role", list(Role))
def test_matrice_role_visibilite(client, demo, role):
    assert set(ATTENDU_LECTURE) == set(Role), "chaque rôle doit avoir son attendu"
    documents = {v: _document(v) for v in Visibilite.values}
    client.force_login(_compte(f"{role}@example.org", role))
    obtenu = {
        v: client.get(reverse("documents:telecharger", args=[d.pk])).status_code for v, d in documents.items()
    }
    assert obtenu == ATTENDU_LECTURE[role]
    # La liste montre exactement les documents lisibles.
    liste = client.get(reverse("documents:liste"))
    if liste.status_code == 200:
        visibles = {d.visibilite for d in liste.context["documents"]}
        assert visibles == {v for v, code in ATTENDU_LECTURE[role].items() if code == 200}
    else:
        assert liste.status_code == 403


def test_perimetre_batiment(client, demo):
    a, b = Batiment.objects.get(nom="Bâtiment A"), Batiment.objects.get(nom="Bâtiment B")
    doc_a, doc_b, doc_commun = _document("cs", a), _document("cs", b), _document("cs")
    client.force_login(_compte("cs-a@example.org", Role.MEMBRE_CS, batiment=a))
    assert client.get(reverse("documents:telecharger", args=[doc_b.pk])).status_code == 403
    assert client.get(reverse("documents:telecharger", args=[doc_a.pk])).status_code == 200
    liste = client.get(reverse("documents:liste")).context["documents"]
    assert set(liste) == {doc_a, doc_commun}
    # Dépôt hors de son bâtiment refusé.
    reponse = _deposer(client, PDF, batiment=b.pk)
    assert reponse.status_code == 400
    assert not Document.objects.filter(titre="Devis toiture").exists()


@pytest.mark.parametrize("role", [Role.ADMIN, Role.CONTROLEUR, Role.SYNDIC, Role.COPROPRIETAIRE])
def test_depot_refuse_sans_droit_d_ecriture(client, demo, role):
    client.force_login(_compte(f"{role}@example.org", role))
    assert _deposer(client, PDF).status_code == 403
    assert Document.objects.count() == 0


def test_depot_ne_propose_que_les_niveaux_lisibles(client, demo):
    """Le syndic non professionnel ne lit pas les documents réservés au CS : il
    ne peut pas en déposer un (il ne le reverrait plus)."""
    client.force_login(_compte("syndic-np@example.org", Role.SYNDIC_NON_PRO))
    choix = {
        v for v, _ in client.get(reverse("documents:deposer")).context["form"].fields["visibilite"].choices
    }
    assert choix == {Visibilite.COMPTES, Visibilite.TOUS}
    assert _deposer(client, PDF, visibilite=Visibilite.CS).status_code == 400
    assert _deposer(client, PDF, visibilite=Visibilite.COMPTES).status_code == 302

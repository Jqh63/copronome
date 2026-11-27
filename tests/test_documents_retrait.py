"""Remplacement et retrait d'un document : versions, effacement du fichier,
motif obligatoire, journal d'audit et droits sur l'objet."""

import hashlib

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from acces.models import Role
from audit.models import Action, JournalAudit
from copro.models import Batiment
from documents import views
from documents.models import Document, volume_occupe
from tests.test_acces import _compte
from tests.test_documents import PDF, PNG, _deposer

pytestmark = pytest.mark.django_db

PDF2 = PDF.replace(b"1.7", b"1.6")


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def membre(client):
    call_command("charger_demo")
    compte = _compte("cs@example.org", Role.MEMBRE_CS)
    client.force_login(compte)
    return compte


def _remplacer(client, document, contenu=PDF2, nom="devis-v2.pdf", **champs):
    donnees = {"fichier": SimpleUploadedFile(nom, contenu, content_type="application/pdf"), **champs}
    return client.post(reverse("documents:remplacer", args=[document.pk]), donnees)


def _retirer(client, document, motif="Déposé par erreur"):
    return client.post(reverse("documents:retirer", args=[document.pk]), {"motif": motif})


def _existe(document):
    return document.fichier.storage.exists(document.fichier.name)


def test_remplacement_cree_une_version_et_garde_l_ancienne(client, membre):
    _deposer(client, PDF)
    ancien = Document.objects.get()
    assert _remplacer(client, ancien, date_document="2026-11-01").status_code == 302
    nouveau = Document.objects.get(remplace=ancien)
    assert (nouveau.titre, nouveau.categorie, nouveau.visibilite, nouveau.batiment) == (
        ancien.titre,
        ancien.categorie,
        ancien.visibilite,
        ancien.batiment,
    )
    assert nouveau.empreinte == hashlib.sha256(PDF2).hexdigest()
    assert str(nouveau.date_document) == "2026-11-01"
    assert nouveau.depose_par == membre
    # La liste ne montre que la version courante ; l'ancienne reste lisible.
    assert list(client.get(reverse("documents:liste")).context["documents"]) == [nouveau]
    reponse = client.get(reverse("documents:telecharger", args=[ancien.pk]))
    assert reponse.status_code == 200 and b"".join(reponse.streaming_content) == PDF
    entree = JournalAudit.objects.get(action=Action.DOCUMENT_REMPLACE)
    assert entree.objet_id == str(nouveau.pk)
    assert entree.acteur == membre
    assert entree.detail == {
        "remplace": ancien.pk,
        "ancienne_empreinte": ancien.empreinte,
        "empreinte": nouveau.empreinte,
    }


def test_remplacement_verifie_le_contenu_et_refuse_une_ancienne_version(client, membre):
    _deposer(client, PDF)
    ancien = Document.objects.get()
    assert _remplacer(client, ancien, contenu=b"<html><script>x</script></html>").status_code == 400
    assert Document.objects.count() == 1
    _remplacer(client, ancien)
    # Une version déjà remplacée ne se remplace ni ne se retire.
    assert _remplacer(client, ancien, contenu=PNG, nom="x.png").status_code == 410
    assert _retirer(client, ancien).status_code == 410
    assert Document.objects.count() == 2


def test_retrait_efface_le_fichier_et_les_versions_precedentes(
    client, membre, django_capture_on_commit_callbacks
):
    _deposer(client, PDF)
    v1 = Document.objects.get()
    _remplacer(client, v1)
    v2 = Document.objects.get(remplace=v1)
    assert _existe(v1) and _existe(v2)
    with django_capture_on_commit_callbacks(execute=True):
        assert _retirer(client, v2, motif="  Données personnelles  ").status_code == 302
    v1.refresh_from_db()
    v2.refresh_from_db()
    for version in (v1, v2):
        assert version.retire_le is not None and version.retire_par == membre
        assert version.motif_retrait == "Données personnelles"
        assert not _existe(version)
        assert client.get(reverse("documents:telecharger", args=[version.pk])).status_code == 410
    assert list(client.get(reverse("documents:liste")).context["documents"]) == []
    assert volume_occupe() == 0
    entrees = JournalAudit.objects.filter(action=Action.DOCUMENT_RETIRE)
    assert {e.objet_id for e in entrees} == {str(v1.pk), str(v2.pk)}
    assert all(e.detail["motif"] == "Données personnelles" and e.acteur == membre for e in entrees)
    assert {e.detail["empreinte"] for e in entrees} == {v1.empreinte, v2.empreinte}


@pytest.mark.parametrize("motif", ["", "   "])
def test_retrait_exige_un_motif(client, membre, motif, django_capture_on_commit_callbacks):
    _deposer(client, PDF)
    document = Document.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        assert _retirer(client, document, motif=motif).status_code == 400
    document.refresh_from_db()
    assert document.retire_le is None and _existe(document)
    assert not JournalAudit.objects.filter(action=Action.DOCUMENT_RETIRE).exists()


def test_retrait_annule_garde_les_fichiers(client, membre, monkeypatch, django_capture_on_commit_callbacks):
    _deposer(client, PDF)
    v1 = Document.objects.get()
    _remplacer(client, v1)
    v2 = Document.objects.get(remplace=v1)
    journaliser = views.journaliser
    appels = []

    def panne_au_second(*args, **kwargs):
        # La 1re version est traitée en entier, la panne tombe sur la 2e :
        # un effacement fait avant la validation aurait déjà emporté v2.
        appels.append(1)
        if len(appels) == 2:
            raise RuntimeError("journal indisponible")
        return journaliser(*args, **kwargs)

    monkeypatch.setattr("documents.views.journaliser", panne_au_second)
    client.raise_request_exception = False
    with django_capture_on_commit_callbacks(execute=True) as rappels:
        assert _retirer(client, v2).status_code == 500
    assert rappels == [] and len(appels) == 2
    for version in (v1, v2):
        version.refresh_from_db()
        assert version.retire_le is None and _existe(version)
    assert not JournalAudit.objects.filter(action=Action.DOCUMENT_RETIRE).exists()


@pytest.mark.parametrize("role", [Role.ADMIN, Role.CONTROLEUR, Role.SYNDIC, Role.COPROPRIETAIRE])
def test_remplacer_et_retirer_refuses_sans_droit_d_ecriture(client, membre, role):
    _deposer(client, PDF, visibilite="tous")
    document = Document.objects.get()
    client.force_login(_compte(f"{role}@example.org", role))
    assert _remplacer(client, document).status_code == 403
    assert _retirer(client, document).status_code == 403
    assert client.get(reverse("documents:retirer", args=[document.pk])).status_code == 403
    document.refresh_from_db()
    assert document.est_courant and Document.objects.count() == 1


def test_perimetre_batiment_et_lien_d_action(client, membre):
    a, b = Batiment.objects.get(nom="Bâtiment A"), Batiment.objects.get(nom="Bâtiment B")
    _deposer(client, PDF, batiment=b.pk)
    doc_b = Document.objects.get()
    client.force_login(_compte("cs-a@example.org", Role.MEMBRE_CS, batiment=a))
    assert _remplacer(client, doc_b).status_code == 403
    assert _retirer(client, doc_b).status_code == 403
    # Le membre du bâtiment B voit les liens ; un contrôleur qui lit le
    # document ne les voit pas.
    client.force_login(_compte("cs-b@example.org", Role.MEMBRE_CS, batiment=b))
    page = client.get(reverse("documents:liste")).content.decode()
    assert reverse("documents:retirer", args=[doc_b.pk]) in page
    doc_b.visibilite = "comptes"
    doc_b.save()
    client.force_login(_compte("ctrl@example.org", Role.CONTROLEUR))
    page = client.get(reverse("documents:liste")).content.decode()
    assert doc_b.titre in page and reverse("documents:retirer", args=[doc_b.pk]) not in page

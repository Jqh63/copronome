from django.db import transaction
from django.http import FileResponse, HttpResponseGone
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from acces.droits import (
    ECRIRE,
    LIRE,
    batiments_visibles,
    exige,
    filtre_documents,
    peut,
    verifier,
    visibilites_lisibles,
)
from audit.models import Action, journaliser
from documents.conservation import echeance, erreur_encore_possible, retrait_bloque
from documents.forms import DocumentForm, RaisonRetrait, RemplacementForm, RetraitForm, renseigner_fichier
from documents.models import Categorie, Document


@exige(LIRE, "documents")
def liste(request):
    # Seules les versions courantes : une version remplacée se lit depuis la
    # suivante, un document retiré n'a plus de fichier.
    documents = (
        Document.objects.filter(filtre_documents(request.user))
        .filter(retire_le__isnull=True, remplace_par__isnull=True)
        .select_related("batiment", "remplace")
    )
    categorie = request.GET.get("categorie")
    if categorie:
        documents = documents.filter(categorie=categorie)
    documents = list(documents)
    for document in documents:
        document.modifiable = peut(request.user, ECRIRE, "documents", document)
        document.conservation = echeance(document)
    return render(
        request,
        "documents/liste.html",
        {"documents": documents, "categorie": categorie, "categories": Categorie.choices},
    )


@exige(ECRIRE, "documents")
def deposer(request):
    form = DocumentForm(
        request.POST or None,
        request.FILES or None,
        batiments_visibles=batiments_visibles(request.user, ECRIRE, "documents"),
        visibilites=visibilites_lisibles(request.user),
    )
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        verifier(request.user, ECRIRE, "documents", document)
        document.depose_par = request.user
        with transaction.atomic():
            document.save()
            journaliser(
                Action.DOCUMENT_DEPOSE,
                acteur=request.user,
                objet=document,
                empreinte=document.empreinte,
                categorie=document.categorie,
                visibilite=document.visibilite,
            )
        return redirect("documents:liste")
    return render(request, "documents/deposer.html", {"form": form}, status=400 if form.errors else 200)


def _courant_a_modifier(request, pk):
    """Document chargé depuis l'URL, droit d'écriture vérifié sur l'objet
    avant tout autre test (un 410 ne révèle rien à qui n'a pas le droit)."""
    document = get_object_or_404(Document, pk=pk)
    verifier(request.user, ECRIRE, "documents", document)
    return document


@exige(ECRIRE, "documents")
def remplacer(request, pk):
    ancien = _courant_a_modifier(request, pk)
    if not ancien.est_courant:
        return HttpResponseGone("Ce document a déjà été remplacé ou retiré.")
    form = RemplacementForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Verrou : deux remplacements simultanés ne créent pas deux suites.
            ancien = Document.objects.select_for_update().get(pk=ancien.pk)
            if not ancien.est_courant:
                return HttpResponseGone("Ce document a déjà été remplacé ou retiré.")
            nouveau = Document(
                titre=ancien.titre,
                categorie=ancien.categorie,
                visibilite=ancien.visibilite,
                batiment=ancien.batiment,
                date_document=form.cleaned_data["date_document"] or ancien.date_document,
                valide_jusquau=form.cleaned_data["valide_jusquau"] or ancien.valide_jusquau,
                depose_par=request.user,
                remplace=ancien,
            )
            renseigner_fichier(nouveau, form.cleaned_data["fichier"], form.type_mime)
            nouveau.save()
            journaliser(
                Action.DOCUMENT_REMPLACE,
                acteur=request.user,
                objet=nouveau,
                remplace=ancien.pk,
                ancienne_empreinte=ancien.empreinte,
                empreinte=nouveau.empreinte,
            )
        return redirect("documents:liste")
    return render(
        request,
        "documents/remplacer.html",
        {"form": form, "document": ancien},
        status=400 if form.errors else 200,
    )


@exige(ECRIRE, "documents")
def retirer(request, pk):
    document = _courant_a_modifier(request, pk)
    if not document.est_courant:
        return HttpResponseGone("Ce document a déjà été remplacé ou retiré.")
    form = RetraitForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        motif = form.cleaned_data["motif"]
        raison = form.cleaned_data["raison"]
        with transaction.atomic():
            document = Document.objects.select_for_update().get(pk=document.pk)
            if not document.est_courant:
                return HttpResponseGone("Ce document a déjà été remplacé ou retiré.")
            refus = _refus_conservation(document, raison, timezone.now())
            if refus:
                form.add_error("raison", refus)
                return _page_retrait(request, form, document, status=409)
            # Le retrait emporte les versions précédentes : sinon un document
            # retiré pour données personnelles resterait lisible par l'ancienne.
            retires = [document, *document.versions_precedentes()]
            maintenant = timezone.now()
            stockage = document.fichier.storage
            for version in retires:
                fichier = version.fichier.name
                version.retire_le = maintenant
                version.retire_par = request.user
                version.motif_retrait = motif
                version.save(update_fields=["retire_le", "retire_par", "motif_retrait"])
                journaliser(
                    Action.DOCUMENT_RETIRE,
                    acteur=request.user,
                    objet=version,
                    empreinte=version.empreinte,
                    motif=motif,
                    raison=raison,
                )
                # Effacement après validation : un retrait annulé garde son fichier.
                transaction.on_commit(lambda nom=fichier: stockage.delete(nom))
        return redirect("documents:liste")
    return _page_retrait(request, form, document, status=400 if form.errors else 200)


def _page_retrait(request, form, document, status):
    return render(
        request,
        "documents/retirer.html",
        {
            "form": form,
            "document": document,
            "versions": list(document.versions_precedentes()),
            "conservation": echeance(document),
        },
        status=status,
    )


def _refus_conservation(document, raison, maintenant):
    """Seul décideur du blocage (conservation.py porte les durées)."""
    if raison == RaisonRetrait.EFFACEMENT:
        return None
    if raison == RaisonRetrait.ERREUR:
        if not erreur_encore_possible(document, maintenant):
            return "Le délai de 48 h pour une erreur de dépôt est passé."
        if document.remplace_id is not None:
            return "Ce document a des versions précédentes : déposez une version corrigée avec « Remplacer »."
        return None
    return retrait_bloque(document, maintenant)


@exige(LIRE, "documents")
def telecharger(request, pk):
    document = get_object_or_404(Document, pk=pk)
    verifier(request.user, LIRE, "documents", document)
    if document.retire_le is not None:
        return HttpResponseGone("Ce document a été retiré.")
    # Toujours en pièce jointe, jamais affiché dans la page (ADR, fichier piégé).
    reponse = FileResponse(
        document.fichier.open("rb"),
        as_attachment=True,
        filename=document.nom_origine,
        content_type=document.type_mime,
    )
    reponse["Cache-Control"] = "private, no-store"
    return reponse

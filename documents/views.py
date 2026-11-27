from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from acces.droits import ECRIRE, LIRE, batiments_visibles, exige, filtre_documents, verifier
from audit.models import Action, journaliser
from documents.forms import DocumentForm
from documents.models import Categorie, Document


@exige(LIRE, "documents")
def liste(request):
    documents = Document.objects.filter(filtre_documents(request.user)).select_related("batiment")
    categorie = request.GET.get("categorie")
    if categorie:
        documents = documents.filter(categorie=categorie)
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


@exige(LIRE, "documents")
def telecharger(request, pk):
    document = get_object_or_404(Document, pk=pk)
    verifier(request.user, LIRE, "documents", document)
    # Toujours en pièce jointe, jamais affiché dans la page (ADR, fichier piégé).
    reponse = FileResponse(
        document.fichier.open("rb"),
        as_attachment=True,
        filename=document.nom_origine,
        content_type=document.type_mime,
    )
    reponse["Cache-Control"] = "private, no-store"
    return reponse

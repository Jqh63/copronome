import csv
from types import SimpleNamespace

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from acces.droits import ECRIRE, LIRE, batiments_visibles, exige, peut, verifier
from audit.views import _cellule
from copro.models import Batiment
from eau.forms import CompteurForm, PeriodeForm, ReleveForm, TourneeForm
from eau.models import Compteur, Releve, consommation, historique


def visibles(utilisateur, action=LIRE):
    compteurs = Compteur.objects.select_related("lot__batiment", "partie_commune__batiment")
    ids = batiments_visibles(utilisateur, action, "eau")
    if ids == set():
        return compteurs.none()
    if ids is not None:
        compteurs = compteurs.filter(lot__batiment_id__in=ids) | compteurs.filter(
            partie_commune__batiment_id__in=ids
        )
    return compteurs


@exige(LIRE, "eau")
def liste(request):
    lignes = []
    for compteur in visibles(request.user).filter(actif=True):
        histo = historique(compteur)
        lignes.append(
            {
                "compteur": compteur,
                "dernier": histo[-1] if histo else None,
                "baisses": sum(1 for ligne in histo if ligne["baisse"]),
            }
        )
    ids = batiments_visibles(request.user, ECRIRE, "eau")
    batiments = Batiment.objects.all() if ids is None else Batiment.objects.filter(pk__in=ids)
    return render(
        request,
        "eau/liste.html",
        {
            "lignes": lignes,
            "batiments_tournee": batiments,
            "periode": PeriodeForm(),
            "peut_ecrire": peut(request.user, ECRIRE, "eau"),
        },
    )


def _page_compteur(request, compteur, form, status=200):
    return render(
        request,
        "eau/compteur.html",
        {
            "compteur": compteur,
            "historique": historique(compteur),
            "corriges": compteur.releves.filter(correction__isnull=False).select_related("correction"),
            "form": form,
            "corrige": form.initial.get("corrige") if form else None,
            "peut_ecrire": peut(request.user, ECRIRE, "eau", compteur),
        },
        status=status,
    )


@exige(LIRE, "eau")
def compteur(request, pk):
    compteur = get_object_or_404(Compteur, pk=pk)
    verifier(request.user, LIRE, "eau", compteur)
    corrige = None
    if request.GET.get("corrige"):
        corrige = get_object_or_404(
            compteur.releves.filter(correction__isnull=True), pk=request.GET["corrige"]
        )
    form = ReleveForm(initial={"releve_le": timezone.localdate(), "corrige": corrige})
    return _page_compteur(request, compteur, form)


@exige(ECRIRE, "eau")
def ajouter_releve(request, pk):
    compteur = get_object_or_404(Compteur, pk=pk)
    verifier(request.user, ECRIRE, "eau", compteur)
    if request.method != "POST":
        return redirect("eau:compteur", pk=pk)
    corrige = None
    if request.POST.get("corrige"):
        corrige = get_object_or_404(
            compteur.releves.filter(correction__isnull=True), pk=request.POST["corrige"]
        )
    form = ReleveForm(request.POST, initial={"corrige": corrige})
    if form.is_valid():
        releve = form.save(commit=False)
        releve.compteur, releve.corrige, releve.auteur = compteur, corrige, request.user
        releve.save()
        return redirect("eau:compteur", pk=pk)
    return _page_compteur(request, compteur, form, status=400)


@exige(ECRIRE, "eau")
def deposer(request, pk):
    """Compteur déposé ou remplacé : il sort des tournées, ses relevés restent."""
    compteur = get_object_or_404(Compteur, pk=pk)
    verifier(request.user, ECRIRE, "eau", compteur)
    if request.method == "POST" and compteur.actif:
        compteur.actif = False
        compteur.save(update_fields=["actif"])
    return redirect("eau:compteur", pk=pk)


@exige(ECRIRE, "eau")
def creer_compteur(request):
    form = CompteurForm(
        request.POST or None, batiments_visibles=batiments_visibles(request.user, ECRIRE, "eau")
    )
    if request.method == "POST" and form.is_valid():
        compteur = form.save(commit=False)
        verifier(request.user, ECRIRE, "eau", compteur)
        compteur.save()
        return redirect("eau:compteur", pk=compteur.pk)
    return render(request, "eau/creer_compteur.html", {"form": form}, status=400 if form.errors else 200)


@exige(ECRIRE, "eau")
def tournee(request, batiment):
    batiment = get_object_or_404(Batiment, pk=batiment)
    # Un Batiment n'a pas d'attribut `batiment_id` : sans cet objet de
    # périmètre, `verifier` accepterait tout bâtiment.
    verifier(request.user, ECRIRE, "eau", SimpleNamespace(batiment_id=batiment.pk))
    compteurs = (
        Compteur.objects.filter(actif=True, lot__batiment=batiment)
        | Compteur.objects.filter(actif=True, partie_commune__batiment=batiment)
    ).select_related("lot", "partie_commune")
    form = TourneeForm(request.POST or None, compteurs=compteurs)
    if request.method == "POST" and form.is_valid():
        saisies = form.saisies()
        if saisies:
            with transaction.atomic():
                for compteur, index in saisies:
                    Releve.objects.create(
                        compteur=compteur,
                        releve_le=form.cleaned_data["releve_le"],
                        index=index,
                        source=form.cleaned_data["source"],
                        auteur=request.user,
                    )
            return redirect("eau:liste")
        form.add_error(None, "Aucun index saisi.")
    return render(
        request,
        "eau/tournee.html",
        {"batiment": batiment, "form": form},
        status=400 if form.errors else 200,
    )


@exige(LIRE, "eau")
def exporter(request):
    """m³ par lot sur une période, pour la clé « eau » du logiciel de comptabilité."""
    form = PeriodeForm(request.GET)
    if not form.is_valid():
        return HttpResponse("Période invalide.", status=400, content_type="text/plain; charset=utf-8")
    debut, fin = form.cleaned_data["debut"], form.cleaned_data["fin"]
    nom = f"eau-{debut:%Y-%m-%d}-{fin:%Y-%m-%d}.csv"
    reponse = HttpResponse(content_type="text/csv; charset=utf-8")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    reponse["Cache-Control"] = "private, no-store"
    reponse.write("﻿")  # BOM : accents lisibles à l'ouverture dans un tableur
    ecrivain = csv.writer(reponse, delimiter=";")
    ecrivain.writerow(["lot", "lieu", "compteur", "date_debut", "index_debut", "date_fin", "index_fin", "m3"])
    for compteur in visibles(request.user).order_by("lot__numero", "numero"):
        m3, releve_debut, releve_fin = consommation(compteur, debut, fin)
        if releve_debut is None and releve_fin is None:
            continue  # compteur sans relevé sur la période ni avant (déposé ou pas encore relevé)
        ecrivain.writerow(
            _cellule(v)
            for v in (
                compteur.lot.numero if compteur.lot_id else "",
                compteur.lieu,
                compteur.numero,
                f"{releve_debut.releve_le:%Y-%m-%d}" if releve_debut else "",
                releve_debut.index if releve_debut else "",
                f"{releve_fin.releve_le:%Y-%m-%d}" if releve_fin else "",
                releve_fin.index if releve_fin else "",
                m3 if m3 is not None else "relevé manquant",
            )
        )
    return reponse

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from acces.droits import ECRIRE, LIRE, batiments_visibles, exige, verifier
from echeances.controles_types import CONTROLES_TYPES, PAR_CODE
from echeances.forms import EcheanceForm, RealisationForm
from echeances.models import Echeance, realiser


def visibles(utilisateur, action=LIRE):
    """Échéances du périmètre de l'utilisateur (sert aussi aux rappels)."""
    echeances = Echeance.objects.select_related("batiment", "partie_commune")
    ids = batiments_visibles(utilisateur, action, "echeances")
    if ids == set():
        return echeances.none()  # aucun droit : pas même les échéances communes
    if ids is not None:
        echeances = echeances.filter(batiment_id__in=ids) | echeances.filter(batiment__isnull=True)
    return echeances


@exige(LIRE, "echeances")
def liste(request):
    echeances = visibles(request.user)
    closes = request.GET.get("closes") == "1"
    echeances = echeances.filter(active=not closes)
    return render(
        request,
        "echeances/liste.html",
        {"echeances": echeances, "closes": closes, "aujourdhui": timezone.localdate()},
    )


@exige(LIRE, "echeances")
def detail(request, pk):
    echeance = get_object_or_404(Echeance, pk=pk)
    verifier(request.user, LIRE, "echeances", echeance)
    return render(
        request,
        "echeances/detail.html",
        {
            "echeance": echeance,
            "realisations": echeance.realisations.select_related("auteur"),
            "form": RealisationForm(),
            "aujourdhui": timezone.localdate(),
        },
    )


@exige(ECRIRE, "echeances")
def creer(request):
    modele = request.GET.get("modele")
    if modele and modele not in PAR_CODE:
        raise Http404("Contrôle type inconnu.")
    form = EcheanceForm(
        request.POST or None,
        initial=PAR_CODE[modele].initial() if modele else None,
        batiments_visibles=batiments_visibles(request.user, ECRIRE, "echeances"),
    )
    if request.method == "POST" and form.is_valid():
        echeance = form.save(commit=False)
        verifier(request.user, ECRIRE, "echeances", echeance)
        echeance.save()
        return redirect("echeances:detail", pk=echeance.pk)
    return render(
        request,
        "echeances/creer.html",
        {"form": form, "controles_types": CONTROLES_TYPES, "modele": modele},
        status=400 if form.errors else 200,
    )


@exige(ECRIRE, "echeances")
def realiser_echeance(request, pk):
    echeance = get_object_or_404(Echeance, pk=pk)
    verifier(request.user, ECRIRE, "echeances", echeance)
    if request.method != "POST":
        return redirect("echeances:detail", pk=pk)
    form = RealisationForm(request.POST)
    if form.is_valid() and echeance.active:
        realiser(echeance, auteur=request.user, **form.cleaned_data)
        return redirect("echeances:detail", pk=pk)
    if not echeance.active:
        form.add_error(None, "Échéance déjà close.")
    return render(
        request,
        "echeances/detail.html",
        {
            "echeance": echeance,
            "realisations": echeance.realisations.select_related("auteur"),
            "form": form,
            "aujourdhui": timezone.localdate(),
        },
        status=400,
    )

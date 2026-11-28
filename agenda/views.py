import datetime

from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from acces.droits import ECRIRE, LIRE, batiments_visibles, exige, peut, public, verifier
from acces.middleware import mfa_obligatoire
from agenda import ical
from agenda.forms import EvenementForm
from agenda.models import Evenement, JetonAgenda
from copro.identite import nom_affiche
from echeances.views import visibles as echeances_visibles


def _visibles(utilisateur):
    evenements = Evenement.objects.select_related("batiment", "incident")
    ids = batiments_visibles(utilisateur, LIRE, "agenda")
    if ids == set():
        return evenements.none()
    if ids is not None:
        evenements = evenements.filter(batiment_id__in=ids) | evenements.filter(batiment__isnull=True)
    return evenements


@exige(LIRE, "agenda")
def liste(request):
    depuis = timezone.now() - datetime.timedelta(days=1)
    return render(
        request,
        "agenda/liste.html",
        {
            "evenements": _visibles(request.user).filter(debut__gte=depuis),
            "a_un_lien": JetonAgenda.objects.filter(utilisateur=request.user).exists(),
        },
    )


@exige(ECRIRE, "agenda")
def creer(request):
    return _formulaire(request, None)


@exige(ECRIRE, "agenda")
def modifier(request, pk):
    evenement = get_object_or_404(Evenement, pk=pk)
    verifier(request.user, ECRIRE, "agenda", evenement)
    return _formulaire(request, evenement)


def _formulaire(request, evenement):
    form = EvenementForm(
        request.POST or None,
        instance=evenement,
        batiments_visibles=batiments_visibles(request.user, ECRIRE, "agenda"),
    )
    if request.method == "POST" and form.is_valid():
        evenement = form.save(commit=False)
        verifier(request.user, ECRIRE, "agenda", evenement)
        if evenement.pk is None:
            evenement.cree_par = request.user
        evenement.save()
        return redirect("agenda:liste")
    return render(
        request,
        "agenda/formulaire.html",
        {"form": form, "evenement": evenement},
        status=400 if form.errors else 200,
    )


@exige(LIRE, "agenda")
def lien_ical(request):
    """POST : génère un nouveau lien (révoque l'ancien) et l'affiche une fois ;
    POST avec `revoquer` : supprime le lien."""
    if request.method != "POST":
        return redirect("agenda:liste")
    if "revoquer" in request.POST:
        JetonAgenda.objects.filter(utilisateur=request.user).delete()
        return redirect("agenda:liste")
    jeton = JetonAgenda.generer(request.user)
    lien = request.build_absolute_uri(reverse("agenda:ical", args=[jeton]))
    return render(request, "agenda/lien.html", {"lien": lien})


def _compte_valide(utilisateur):
    if not utilisateur.is_active:
        return False
    # Même règle que le middleware : un compte dont le second facteur
    # obligatoire a disparu ne lit plus rien, lien iCal compris.
    return not mfa_obligatoire(utilisateur) or is_mfa_enabled(utilisateur, types=["totp", "webauthn"])


@public
def flux_ical(request, jeton):
    """Flux iCal du compte qui porte le jeton : l'appli d'agenda ne se
    connecte pas, le jeton tient lieu de session pour ce seul flux en lecture."""
    lien = JetonAgenda.trouver(jeton)
    if lien is None or not _compte_valide(lien.utilisateur):
        raise Http404
    utilisateur = lien.utilisateur
    entrees = []
    if peut(utilisateur, LIRE, "agenda"):
        depuis = timezone.now() - datetime.timedelta(days=90)
        for e in _visibles(utilisateur).filter(debut__gte=depuis):
            entrees.append(
                {
                    "uid": f"agenda-{e.pk}@{settings.INSTANCE_ID}.copronome",
                    "titre": e.titre,
                    "debut": e.debut,
                    "fin": e.fin,
                    "lieu": e.lieu,
                    "description": e.description,
                    "annule": e.annule,
                }
            )
    if peut(utilisateur, LIRE, "echeances"):
        for e in echeances_visibles(utilisateur).filter(active=True):
            entrees.append(
                {
                    "uid": f"echeance-{e.pk}@{settings.INSTANCE_ID}.copronome",
                    "titre": f"Échéance : {e.titre}",
                    "debut": e.prochaine_le,
                }
            )
    reponse = HttpResponse(
        ical.calendrier(nom_affiche(), entrees), content_type="text/calendar; charset=utf-8"
    )
    reponse["Cache-Control"] = "private, no-store"
    reponse["Referrer-Policy"] = "no-referrer"
    return reponse

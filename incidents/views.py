from django.shortcuts import get_object_or_404, redirect, render

from acces.droits import ECRIRE, LIRE, batiments_visibles, exige, verifier
from incidents.forms import EvenementForm, IncidentForm
from incidents.models import Evenement, Incident, journaliser


def _visibles(utilisateur):
    incidents = Incident.objects.select_related("batiment", "lot", "partie_commune")
    ids = batiments_visibles(utilisateur, LIRE, "incidents")
    if ids is not None:
        incidents = incidents.filter(batiment_id__in=ids) | incidents.filter(batiment__isnull=True)
    return incidents


@exige(LIRE, "incidents")
def liste(request):
    incidents = _visibles(request.user)
    statut = request.GET.get("statut")
    if statut:
        incidents = incidents.filter(statut=statut)
    return render(request, "incidents/liste.html", {"incidents": incidents, "statut": statut})


@exige(LIRE, "incidents")
def detail(request, pk):
    incident = get_object_or_404(Incident, pk=pk)
    verifier(request.user, LIRE, "incidents", incident)
    return render(
        request,
        "incidents/detail.html",
        {
            "incident": incident,
            "evenements": incident.evenements.select_related("auteur"),
            "form": EvenementForm(),
        },
    )


@exige(ECRIRE, "incidents")
def creer(request):
    form = IncidentForm(
        request.POST or None, batiments_visibles=batiments_visibles(request.user, ECRIRE, "incidents")
    )
    if request.method == "POST" and form.is_valid():
        incident = form.save(commit=False)
        verifier(request.user, ECRIRE, "incidents", incident)
        incident.signale_par = request.user
        incident.save()
        journaliser(incident, Evenement.Type.CREATION, request.user)
        return redirect("incidents:detail", pk=incident.pk)
    return render(request, "incidents/creer.html", {"form": form})


@exige(ECRIRE, "incidents")
def ajouter_evenement(request, pk):
    incident = get_object_or_404(Incident, pk=pk)
    verifier(request.user, ECRIRE, "incidents", incident)
    if request.method != "POST":
        return redirect("incidents:detail", pk=pk)
    form = EvenementForm(request.POST)
    if form.is_valid():
        journaliser(incident, auteur=request.user, **form.cleaned_data)
        return redirect("incidents:detail", pk=pk)
    return render(
        request,
        "incidents/detail.html",
        {"incident": incident, "evenements": incident.evenements.select_related("auteur"), "form": form},
        status=400,
    )

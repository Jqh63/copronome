from django import forms
from django.shortcuts import redirect, render
from django.urls import reverse

from acces.droits import ECRIRE, LIRE, batiments_visibles, exige
from audit.models import Action, journaliser
from copro.models import Copropriete, Lot


@exige(LIRE, "structure")
def liste_lots(request):
    lots = Lot.objects.select_related("batiment").prefetch_related("tantiemes__cle")
    visibles = batiments_visibles(request.user, LIRE, "structure")
    if visibles is not None:
        lots = lots.filter(batiment_id__in=visibles)
    return render(request, "copro/lots.html", {"lots": lots})


class IdentiteForm(forms.ModelForm):
    class Meta:
        model = Copropriete
        fields = ["nom", "commune", "code_insee", "adresse", "immatriculation"]


@exige(ECRIRE, "structure")
def identite(request):
    """Identité de l'instance, saisie dans l'app par qui gère la structure
    (président du CS, syndic non professionnel) : sans commande ni admin. Le
    nom s'affiche dans les mails, d'où la trace de chaque changement."""
    copropriete = Copropriete.courante()
    form = IdentiteForm(request.POST or None, instance=copropriete)
    if request.method == "POST" and form.is_valid():
        changes = {c: [str(form.initial.get(c, "")), str(form.cleaned_data[c])] for c in form.changed_data}
        copropriete = form.save()
        if changes:
            journaliser(Action.COPROPRIETE_MODIFIEE, request.user, copropriete, champs=changes)
        return redirect(reverse("identite") + "?enregistre=1")
    contexte = {"form": form, "enregistre": request.GET.get("enregistre") == "1"}
    return render(request, "copro/identite.html", contexte, status=400 if form.errors else 200)

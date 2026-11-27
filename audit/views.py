"""Consultation et export du journal d'audit (droit « lire audit » :
admin technique et président du CS, cf. acces.droits)."""

import csv
import json

from django import forms
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from acces.droits import LIRE, exige
from audit.models import Action, JournalAudit, journaliser

PAR_PAGE = 100


class FiltreForm(forms.Form):
    action = forms.ChoiceField(choices=[("", "Toutes")] + Action.choices, required=False)
    acteur = forms.CharField(max_length=254, required=False, help_text="Identifiant, ou une partie")
    du = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    au = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))


def _filtrer(request):
    form = FiltreForm(request.GET or None)
    entrees = JournalAudit.objects.all()
    filtres = {}
    if form.is_valid():
        filtres = {k: v for k, v in form.cleaned_data.items() if v}
        if "action" in filtres:
            entrees = entrees.filter(action=filtres["action"])
        if "acteur" in filtres:
            entrees = entrees.filter(acteur_nom__icontains=filtres["acteur"])
        if "du" in filtres:
            entrees = entrees.filter(cree_le__date__gte=filtres["du"])
        if "au" in filtres:
            entrees = entrees.filter(cree_le__date__lte=filtres["au"])
    return form, entrees, filtres


@exige(LIRE, "audit")
def journal(request):
    form, entrees, _ = _filtrer(request)
    page = Paginator(entrees, PAR_PAGE).get_page(request.GET.get("page"))
    # Paramètres de filtre à garder dans les liens de pagination et d'export.
    parametres = request.GET.copy()
    parametres.pop("page", None)
    return render(
        request,
        "audit/journal.html",
        {"form": form, "page": page, "parametres": parametres.urlencode()},
        status=400 if form.errors else 200,
    )


def _cellule(valeur):
    # Un tableur exécute une cellule qui commence par = + - @ (injection de
    # formule, OWASP « CSV Injection ») : on la préfixe d'une apostrophe.
    texte = str(valeur)
    return "'" + texte if texte[:1] in ("=", "+", "-", "@", "\t", "\r") else texte


@exige(LIRE, "audit")
def exporter(request):
    form, entrees, filtres = _filtrer(request)
    if form.errors:
        return HttpResponse("Filtre invalide.", status=400, content_type="text/plain; charset=utf-8")
    entrees = list(entrees)
    # L'export fait sortir le journal de l'application : il se journalise
    # lui-même, avant l'envoi, avec les filtres et le nombre de lignes.
    journaliser(
        Action.JOURNAL_EXPORTE,
        acteur=request.user,
        filtres={k: str(v) for k, v in filtres.items()},
        lignes=len(entrees),
    )
    nom = f"journal-audit-{timezone.localdate():%Y-%m-%d}.csv"
    reponse = HttpResponse(content_type="text/csv; charset=utf-8")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    reponse["Cache-Control"] = "private, no-store"
    reponse.write("﻿")  # BOM : accents lisibles à l'ouverture dans un tableur
    ecrivain = csv.writer(reponse, delimiter=";")
    ecrivain.writerow(["date", "acteur", "action", "objet_type", "objet_id", "objet", "detail"])
    for e in entrees:
        ecrivain.writerow(
            _cellule(v)
            for v in (
                timezone.localtime(e.cree_le).isoformat(timespec="seconds"),
                e.acteur_nom,
                e.get_action_display(),
                e.objet_type,
                e.objet_id,
                e.objet_libelle,
                json.dumps(e.detail, ensure_ascii=False, sort_keys=True),
            )
        )
    return reponse

import os

from django import forms
from django.conf import settings
from django.db import models
from django.template.defaultfilters import filesizeformat

from documents.models import Document, empreinte_sha256, volume_occupe
from documents.validation import detecter_type


def valider_fichier(fichier):
    """Taille, quota et type détecté sur le contenu ; renvoie le type MIME."""
    if fichier.size > settings.DOCUMENT_TAILLE_MAX:
        raise forms.ValidationError(
            f"Fichier trop gros (maximum {filesizeformat(settings.DOCUMENT_TAILLE_MAX)})."
        )
    if volume_occupe() + fichier.size > settings.DOCUMENTS_QUOTA:
        raise forms.ValidationError(
            f"Espace de stockage plein (quota {filesizeformat(settings.DOCUMENTS_QUOTA)})."
        )
    return detecter_type(fichier)


def renseigner_fichier(document, fichier, type_mime):
    document.type_mime = type_mime
    document.taille = fichier.size
    document.empreinte = empreinte_sha256(fichier)
    document.nom_origine = os.path.basename(fichier.name)[:200]
    document.fichier = fichier  # renommé par upload_to (nom aléatoire)


class DocumentForm(forms.ModelForm):
    fichier = forms.FileField()

    class Meta:
        model = Document
        fields = ["titre", "categorie", "visibilite", "batiment", "date_document", "valide_jusquau"]
        widgets = {
            "date_document": forms.DateInput(attrs={"type": "date"}),
            "valide_jusquau": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, batiments_visibles=None, visibilites=None, **kwargs):
        super().__init__(*args, **kwargs)
        if visibilites is not None:
            champ = self.fields["visibilite"]
            champ.choices = [(v, libelle) for v, libelle in champ.choices if v in visibilites]
        if batiments_visibles is not None:
            # Un membre limité à un bâtiment ne dépose que dans son périmètre.
            self.fields["batiment"].queryset = self.fields["batiment"].queryset.filter(
                pk__in=batiments_visibles
            )
            self.fields["batiment"].required = True

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        self.type_mime = valider_fichier(fichier)
        return fichier

    def save(self, commit=True):
        document = super().save(commit=False)
        renseigner_fichier(document, self.cleaned_data["fichier"], self.type_mime)
        if commit:
            document.save()
        return document


class RemplacementForm(forms.Form):
    """Nouvelle version d'un document : titre, catégorie, visibilité et
    bâtiment sont repris de l'ancienne (le périmètre ne change pas en route)."""

    fichier = forms.FileField()
    date_document = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Date portée par le document",
    )
    valide_jusquau = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Fin de validité ou d'effet, si elle change",
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        self.type_mime = valider_fichier(fichier)
        return fichier


class RaisonRetrait(models.TextChoices):
    FIN = "fin", "Fin de la durée de conservation"
    ERREUR = "erreur", "Déposé par erreur (dans les 48 h, document sans version précédente)"
    EFFACEMENT = "effacement", "Effacement imposé (RGPD, décision de justice)"


class RetraitForm(forms.Form):
    raison = forms.ChoiceField(choices=RaisonRetrait.choices, widget=forms.RadioSelect)
    motif = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obligatoire, gardé dans le journal (ex. : déposé par erreur, données personnelles).",
    )

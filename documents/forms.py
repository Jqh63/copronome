import os

from django import forms
from django.conf import settings
from django.template.defaultfilters import filesizeformat

from documents.models import Document, empreinte_sha256, volume_occupe
from documents.validation import detecter_type


class DocumentForm(forms.ModelForm):
    fichier = forms.FileField()

    class Meta:
        model = Document
        fields = ["titre", "categorie", "visibilite", "batiment", "date_document"]
        widgets = {"date_document": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, batiments_visibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if batiments_visibles is not None:
            # Un membre limité à un bâtiment ne dépose que dans son périmètre.
            self.fields["batiment"].queryset = self.fields["batiment"].queryset.filter(
                pk__in=batiments_visibles
            )
            self.fields["batiment"].required = True

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if fichier.size > settings.DOCUMENT_TAILLE_MAX:
            raise forms.ValidationError(
                f"Fichier trop gros (maximum {filesizeformat(settings.DOCUMENT_TAILLE_MAX)})."
            )
        if volume_occupe() + fichier.size > settings.DOCUMENTS_QUOTA:
            raise forms.ValidationError(
                f"Espace de stockage plein (quota {filesizeformat(settings.DOCUMENTS_QUOTA)})."
            )
        self.type_mime = detecter_type(fichier)
        return fichier

    def save(self, commit=True):
        document = super().save(commit=False)
        fichier = self.cleaned_data["fichier"]
        document.type_mime = self.type_mime
        document.taille = fichier.size
        document.empreinte = empreinte_sha256(fichier)
        document.nom_origine = os.path.basename(fichier.name)[:200]
        document.fichier = fichier  # renommé par upload_to (nom aléatoire)
        if commit:
            document.save()
        return document

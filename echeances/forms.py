from django import forms
from django.utils import timezone

from echeances.models import Echeance


class EcheanceForm(forms.ModelForm):
    class Meta:
        model = Echeance
        fields = [
            "titre",
            "type",
            "prochaine_le",
            "periodicite_mois",
            "rappel_jours",
            "reference",
            "batiment",
            "partie_commune",
            "notes",
        ]
        widgets = {"prochaine_le": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, batiments_visibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if batiments_visibles is not None:
            self.fields["batiment"].queryset = self.fields["batiment"].queryset.filter(
                pk__in=batiments_visibles
            )
            self.fields["batiment"].required = True
            self.fields["partie_commune"].queryset = self.fields["partie_commune"].queryset.filter(
                batiment_id__in=batiments_visibles
            )


class RealisationForm(forms.Form):
    realisee_le = forms.DateField(
        label="Réalisée le", initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"})
    )
    note = forms.CharField(widget=forms.Textarea, required=False)

    def clean_realisee_le(self):
        date = self.cleaned_data["realisee_le"]
        if date > timezone.localdate():
            raise forms.ValidationError("Une réalisation ne peut pas être datée dans le futur.")
        return date

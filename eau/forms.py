from django import forms
from django.utils import timezone

from eau.models import Compteur, Releve


def _pas_dans_le_futur(date):
    if date > timezone.localdate():
        raise forms.ValidationError("Un relevé ne peut pas être daté dans le futur.")
    return date


class CompteurForm(forms.ModelForm):
    class Meta:
        model = Compteur
        fields = ["numero", "lot", "partie_commune", "emplacement"]

    def __init__(self, *args, batiments_visibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if batiments_visibles is not None:
            self.fields["lot"].queryset = self.fields["lot"].queryset.filter(
                batiment_id__in=batiments_visibles
            )
            self.fields["partie_commune"].queryset = self.fields["partie_commune"].queryset.filter(
                batiment_id__in=batiments_visibles
            )


class ReleveForm(forms.ModelForm):
    class Meta:
        model = Releve
        fields = ["releve_le", "index", "source", "note"]
        widgets = {"releve_le": forms.DateInput(attrs={"type": "date"})}

    def clean_releve_le(self):
        return _pas_dans_le_futur(self.cleaned_data["releve_le"])


class TourneeForm(forms.Form):
    """Une date et une source pour tout un bâtiment, un index par compteur
    (vide = compteur non relevé)."""

    releve_le = forms.DateField(
        label="Relevé le", initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"})
    )
    source = forms.ChoiceField(choices=Releve.Source.choices, initial=Releve.Source.CS)

    def __init__(self, *args, compteurs=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.compteurs = list(compteurs)
        for compteur in self.compteurs:
            self.fields[f"index_{compteur.pk}"] = forms.DecimalField(
                label=f"{compteur.numero} — {compteur.lieu}",
                required=False,
                min_value=0,
                max_digits=10,
                decimal_places=3,
            )

    def clean_releve_le(self):
        return _pas_dans_le_futur(self.cleaned_data["releve_le"])

    def saisies(self):
        """(compteur, index) des compteurs relevés."""
        return [
            (c, self.cleaned_data[f"index_{c.pk}"])
            for c in self.compteurs
            if self.cleaned_data.get(f"index_{c.pk}") is not None
        ]


class PeriodeForm(forms.Form):
    debut = forms.DateField(label="Du", widget=forms.DateInput(attrs={"type": "date"}))
    fin = forms.DateField(label="Au", widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        donnees = super().clean()
        if donnees.get("debut") and donnees.get("fin") and donnees["debut"] >= donnees["fin"]:
            raise forms.ValidationError("La fin doit suivre le début.")
        return donnees

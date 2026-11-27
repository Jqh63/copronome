from django import forms

from incidents.models import Evenement, Incident, Statut


class IncidentForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = ["titre", "description", "priorite", "batiment", "partie_commune", "lot", "prestataire"]

    def __init__(self, *args, batiments_visibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if batiments_visibles is not None:
            # Un membre limité à un bâtiment ne crée que dans son périmètre.
            self.fields["batiment"].queryset = self.fields["batiment"].queryset.filter(
                pk__in=batiments_visibles
            )
            self.fields["batiment"].required = True
            self.fields["lot"].queryset = self.fields["lot"].queryset.filter(
                batiment_id__in=batiments_visibles
            )
            self.fields["partie_commune"].queryset = self.fields["partie_commune"].queryset.filter(
                batiment_id__in=batiments_visibles
            )


class EvenementForm(forms.Form):
    type = forms.ChoiceField(choices=[c for c in Evenement.Type.choices if c[0] != Evenement.Type.CREATION])
    texte = forms.CharField(widget=forms.Textarea, required=False)
    nouveau_statut = forms.ChoiceField(choices=[("", "—"), *Statut.choices], required=False)

    def clean(self):
        donnees = super().clean()
        if donnees.get("type") == Evenement.Type.STATUT and not donnees.get("nouveau_statut"):
            self.add_error("nouveau_statut", "Indiquer le nouveau statut.")
        if donnees.get("type") != Evenement.Type.STATUT and not donnees.get("texte"):
            self.add_error("texte", "Texte obligatoire.")
        return donnees

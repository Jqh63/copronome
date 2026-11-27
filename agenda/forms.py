from django import forms

from agenda.models import Evenement


class EvenementForm(forms.ModelForm):
    class Meta:
        model = Evenement
        fields = ["titre", "debut", "fin", "lieu", "description", "batiment", "incident", "annule"]
        widgets = {
            "debut": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "fin": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, batiments_visibles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if batiments_visibles is not None:
            self.fields["batiment"].queryset = self.fields["batiment"].queryset.filter(
                pk__in=batiments_visibles
            )
            self.fields["batiment"].required = True
            self.fields["incident"].queryset = self.fields["incident"].queryset.filter(
                batiment_id__in=batiments_visibles
            )

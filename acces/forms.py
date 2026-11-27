from django import forms
from django.contrib.auth.password_validation import validate_password


class AcceptationInvitationForm(forms.Form):
    mot_de_passe = forms.CharField(label="Mot de passe", widget=forms.PasswordInput, strip=False)
    confirmation = forms.CharField(label="Confirmation", widget=forms.PasswordInput, strip=False)

    def __init__(self, *args, email, **kwargs):
        self.email = email
        super().__init__(*args, **kwargs)

    def clean(self):
        donnees = super().clean()
        mdp, confirmation = donnees.get("mot_de_passe"), donnees.get("confirmation")
        if mdp and confirmation and mdp != confirmation:
            raise forms.ValidationError("Les deux mots de passe diffèrent.")
        if mdp:
            from django.contrib.auth import get_user_model

            validate_password(mdp, user=get_user_model()(username=self.email, email=self.email))
        return donnees

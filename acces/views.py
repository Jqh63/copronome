from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from acces.droits import public
from acces.forms import AcceptationInvitationForm
from acces.models import Affectation, Invitation
from audit.models import Action, journaliser


def _verrouiller(invitation):
    """Relit l'invitation sous verrou : deux envois simultanés du même lien
    ne peuvent pas la consommer deux fois."""
    return Invitation.objects.select_for_update().filter(pk=invitation.pk, utilisee_le__isnull=True).first()


def _affecter(invitation, utilisateur):
    Affectation.objects.get_or_create(
        utilisateur=utilisateur, role=invitation.role, batiment=invitation.batiment
    )
    invitation.utilisee_le = timezone.now()
    invitation.save(update_fields=["utilisee_le"])
    journaliser(Action.INVITATION_ACCEPTEE, acteur=utilisateur, objet=invitation, role=invitation.role)


@public
def accepter_invitation(request, jeton):
    invitation = Invitation.valide(jeton)
    if invitation is None:
        return render(request, "acces/invitation_invalide.html", status=404)

    existant = get_user_model().objects.filter(email__iexact=invitation.email).first()
    if existant:
        # Ajout d'un rôle à un compte existant : seulement par son titulaire connecté.
        if request.user != existant:
            messages.info(
                request, "Un compte existe pour cette adresse : connectez-vous, puis rouvrez le lien."
            )
            return redirect(f"/compte/login/?next={request.path}")
        if request.method == "POST":
            with transaction.atomic():
                invitation = _verrouiller(invitation)
                if invitation is None:
                    return render(request, "acces/invitation_invalide.html", status=404)
                _affecter(invitation, existant)
            messages.success(request, "Rôle ajouté à votre compte.")
            return redirect("accueil")
        return render(request, "acces/invitation_role.html", {"invitation": invitation})

    form = AcceptationInvitationForm(request.POST or None, email=invitation.email)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            invitation = _verrouiller(invitation)
            if invitation is None:
                return render(request, "acces/invitation_invalide.html", status=404)
            utilisateur = get_user_model().objects.create_user(
                username=invitation.email, email=invitation.email, password=form.cleaned_data["mot_de_passe"]
            )
            EmailAddress.objects.create(user=utilisateur, email=invitation.email, verified=True, primary=True)
            _affecter(invitation, utilisateur)
        login(request, utilisateur, backend="allauth.account.auth_backends.AuthenticationBackend")
        return redirect("accueil")
    return render(request, "acces/invitation.html", {"invitation": invitation, "form": form})

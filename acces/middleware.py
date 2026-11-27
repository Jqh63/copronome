"""Second facteur obligatoire pour les rôles qui écrivent ou voient tout.

allauth ne l'impose pas d'office (ADR, § 6) : tant qu'un tel compte n'a
pas enrôlé une passkey ou une application TOTP, toute page autre que
l'enrôlement et la déconnexion renvoie vers la gestion du second facteur.
Une requête htmx reçoit un 401 avec HX-Redirect (pas de fragment servi).
Les superutilisateurs sont traités comme l'admin technique.
"""

from allauth.mfa.utils import is_mfa_enabled
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from acces.models import ROLES_MFA_OBLIGATOIRE

CHEMINS_LIBRES = ("/compte/2fa/", "/compte/logout/", "/compte/reauthenticate/", "/static/", "/sante/")


def mfa_obligatoire(utilisateur):
    if utilisateur.is_superuser:
        return True
    return any(a.role in ROLES_MFA_OBLIGATOIRE for a in utilisateur.affectations.all())


class SecondFacteurObligatoire:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utilisateur = request.user
        if (
            utilisateur.is_authenticated
            and not request.path.startswith(CHEMINS_LIBRES)
            and mfa_obligatoire(utilisateur)
            and not is_mfa_enabled(utilisateur, types=["totp", "webauthn"])
        ):
            cible = reverse("mfa_index")
            if request.headers.get("HX-Request"):
                reponse = HttpResponse(status=401)
                reponse["HX-Redirect"] = cible
                return reponse
            return redirect(cible)
        return self.get_response(request)

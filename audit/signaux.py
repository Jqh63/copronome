"""Branche le journal d'audit sur les événements de compte (Django et allauth).

Les actions métier (invitation, document) appellent `journaliser` là où
elles se font : le journal se lit dans le code qui agit.
"""

from allauth.account import signals as compte
from allauth.mfa import signals as mfa
from django.contrib.auth import signals as auth
from django.dispatch import receiver

from audit.models import Action, journaliser


@receiver(auth.user_logged_in, dispatch_uid="audit_connexion")
def _connexion(sender, request, user, **kwargs):
    journaliser(Action.CONNEXION, acteur=user)


@receiver(auth.user_logged_out, dispatch_uid="audit_deconnexion")
def _deconnexion(sender, request, user, **kwargs):
    journaliser(Action.DECONNEXION, acteur=user)


@receiver(auth.user_login_failed, dispatch_uid="audit_connexion_echec")
def _connexion_echec(sender, credentials, request=None, **kwargs):
    # Django a déjà masqué le mot de passe ; on ne garde que l'identifiant tenté.
    tente = credentials.get("email") or credentials.get("username") or ""
    journaliser(Action.CONNEXION_ECHEC, acteur_nom=str(tente))


@receiver(mfa.authenticator_added, dispatch_uid="audit_mfa_ajout")
def _mfa_ajout(sender, request, user, authenticator, **kwargs):
    journaliser(Action.SECOND_FACTEUR_AJOUTE, acteur=user, type=authenticator.type)


@receiver(mfa.authenticator_removed, dispatch_uid="audit_mfa_retrait")
def _mfa_retrait(sender, request, user, authenticator, **kwargs):
    journaliser(Action.SECOND_FACTEUR_RETIRE, acteur=user, type=authenticator.type)


@receiver(mfa.authentication_failed, dispatch_uid="audit_mfa_echec")
def _mfa_echec(sender, request, user, authenticator, **kwargs):
    journaliser(Action.SECOND_FACTEUR_ECHEC, acteur=user, type=authenticator.type)


@receiver(compte.password_changed, dispatch_uid="audit_mdp_change")
def _mdp_change(sender, request, user, **kwargs):
    journaliser(Action.MOT_DE_PASSE_CHANGE, acteur=user)


@receiver(compte.password_reset, dispatch_uid="audit_mdp_reinit")
def _mdp_reinit(sender, request, user, **kwargs):
    journaliser(Action.MOT_DE_PASSE_REINITIALISE, acteur=user)

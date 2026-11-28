"""Nom de l'instance tel qu'il s'affiche : pages, mails, iCal (ADR domaine et
instances, § 4 et § 6). Le nom de la résidence n'est pas confidentiel ;
l'adresse et le numéro d'immatriculation ne s'affichent qu'aux comptes
connectés (gabarit d'accueil)."""

from email.utils import formataddr, parseaddr

from django.conf import settings

from copro.models import Copropriete

PRODUIT = "Copronome"


def nom_affiche(copropriete=None):
    """« nom (commune) », ou « Copronome » tant que l'identité n'est pas saisie."""
    copropriete = copropriete or Copropriete.courante()
    return str(copropriete) if copropriete else PRODUIT


def expediteur():
    """Adresse d'envoi de l'instance, nom affiché « <copro> via Copronome »."""
    adresse = parseaddr(settings.DEFAULT_FROM_EMAIL)[1] or settings.DEFAULT_FROM_EMAIL
    copropriete = Copropriete.courante()
    nom = f"{copropriete.nom} via {PRODUIT}" if copropriete else PRODUIT
    return formataddr((nom, adresse))


def pied_de_mail(copropriete=None):
    """Pied commun à tous les mails de l'instance (invitation, rappels, allauth) :
    qui écrit, et la règle qui rend un hameçonnage reconnaissable."""
    return (
        "-- \n"
        f"{nom_affiche(copropriete)}, espace géré avec {PRODUIT}\n"
        "Nous ne vous demandons jamais votre mot de passe par mail.\n"
    )


def contexte(request):
    """Processeur de contexte : identité de l'instance, une requête par page."""
    copropriete = Copropriete.courante()
    return {"copropriete": copropriete, "nom_instance": nom_affiche(copropriete)}

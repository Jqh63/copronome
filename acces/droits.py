"""Contrôle d'accès centralisé : la SEULE fonction qui décide (ADR, § 4).

    peut(utilisateur, action, domaine, objet=None) -> bool

- `action` : "lire" ou "ecrire".
- `domaine` : une entrée de DOMAINES.
- `objet` : si fourni, le périmètre est vérifié sur l'objet (anti-IDOR) :
  un objet rattaché à un bâtiment (attribut `batiment_id`) n'est accessible
  qu'aux affectations de toute la copropriété ou de ce bâtiment.

Toute vue passe par le décorateur `exige`, qui marque la vue : le banc
(tests/test_acces.py) parcourt toutes les routes et échoue sur une vue non
marquée. Les règles fines propres à un domaine (incident transmis au
syndic, document public) s'ajoutent ici, jamais dans une vue.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from acces.models import Role

LIRE = "lire"
ECRIRE = "ecrire"

DOMAINES = {
    "structure",  # bâtiments, lots, parties communes, tantièmes
    "personnes",  # fiches des personnes, détentions, occupations
    "incidents",
    "documents",
    "agenda",
    "echeances",
    "eau",  # compteurs et relevés d'index d'eau
    "ag",
    "comptes",  # comptes utilisateurs, affectations, invitations
    "audit",
}
METIER = {"structure", "personnes", "incidents", "documents", "agenda", "echeances", "eau", "ag"}

# Table des droits par rôle : domaine -> actions. Reprend le tableau de l'ADR.
# Les rôles syndic et copropriétaire n'ont encore aucun accès : leurs règles
# portent sur des objets précis (incident transmis, document public) et
# arrivent avec les domaines concernés.
DROITS = {
    # Admin technique : lit tout, n'écrit que les comptes (pas de donnée métier).
    Role.ADMIN: {d: {LIRE} for d in DOMAINES} | {"comptes": {LIRE, ECRIRE}},
    Role.PRESIDENT: {d: {LIRE, ECRIRE} for d in DOMAINES - {"audit"}} | {"audit": {LIRE}},
    # Syndic non professionnel (ADR domaine et instances, § 7) : copropriétaire
    # désigné par l'AG, pouvoirs de gestion du syndic, pas forcément membre du
    # CS. Mêmes droits de domaine que le président, sans les documents réservés
    # au CS (le CS contrôle le syndic). En coopératif, le président du CS est
    # syndic : il cumule les deux affectations.
    Role.SYNDIC_NON_PRO: {d: {LIRE, ECRIRE} for d in DOMAINES - {"audit"}} | {"audit": {LIRE}},
    Role.MEMBRE_CS: {d: {LIRE} for d in METIER}
    | {d: {LIRE, ECRIRE} for d in ("incidents", "documents", "agenda", "echeances", "eau", "ag")},
    # Contrôleur des comptes : lit les relevés qui fondent la clé eau.
    Role.CONTROLEUR: {"documents": {LIRE}, "ag": {LIRE}, "eau": {LIRE}},
    Role.SYNDIC: {},
    Role.COPROPRIETAIRE: {},
}


# Documents : rôles qui lisent chaque niveau de visibilité (champ
# `Document.visibilite`). Le droit de domaine reste exigé en plus : un rôle
# sans « lire documents » ne lit rien, même un document « tous ».
VISIBILITE_DOCUMENTS = {
    "cs": {Role.ADMIN, Role.PRESIDENT, Role.MEMBRE_CS},
    "comptes": {Role.ADMIN, Role.PRESIDENT, Role.MEMBRE_CS, Role.CONTROLEUR, Role.SYNDIC_NON_PRO},
    "tous": set(Role),
}


def _visible(role, domaine, objet):
    if domaine != "documents" or objet is None:
        return True
    return role in VISIBILITE_DOCUMENTS[objet.visibilite]


def _dans_le_perimetre(affectation, objet):
    if affectation.batiment_id is None or objet is None:
        return True
    batiment_id = getattr(objet, "batiment_id", None)
    return batiment_id is None or batiment_id == affectation.batiment_id


def peut(utilisateur, action, domaine, objet=None):
    if domaine not in DOMAINES or action not in (LIRE, ECRIRE):
        raise ValueError(f"Droit inconnu : {action} {domaine}")
    if not utilisateur.is_authenticated or not utilisateur.is_active:
        return False
    for affectation in utilisateur.affectations.all():
        if (
            action in DROITS[affectation.role].get(domaine, ())
            and _dans_le_perimetre(affectation, objet)
            and _visible(affectation.role, domaine, objet)
        ):
            return True
    return False


def verifier(utilisateur, action, domaine, objet=None):
    """Lève PermissionDenied (403) si `peut` refuse : à appeler dans une vue
    sur chaque objet chargé depuis l'URL."""
    if not peut(utilisateur, action, domaine, objet):
        raise PermissionDenied


def exige(action, domaine):
    """Décorateur obligatoire de toute vue métier : refuse l'anonyme (redirigé
    vers la connexion) et vérifie le droit sur le domaine. Le droit sur l'objet
    se vérifie en plus dans la vue avec `verifier`."""
    if domaine not in DOMAINES or action not in (LIRE, ECRIRE):
        raise ValueError(f"Droit inconnu : {action} {domaine}")

    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())
            verifier(request.user, action, domaine)
            return vue(request, *args, **kwargs)

        enveloppe.controle_acces = (action, domaine)
        return enveloppe

    return decorateur


def public(vue):
    """Marque explicitement une vue accessible sans compte (accueil, sonde,
    acceptation d'invitation) : le banc l'accepte, et la liste se relit en diff."""
    vue.controle_acces = "public"
    return vue


def visibilites_lisibles(utilisateur):
    """Niveaux de visibilité de documents que le compte lit : un dépôt ne
    propose que ceux-là (un document déposé doit rester lisible par son auteur)."""
    roles = {a.role for a in utilisateur.affectations.all()}
    return [niveau for niveau, lecteurs in VISIBILITE_DOCUMENTS.items() if roles & lecteurs]


def batiments_visibles(utilisateur, action, domaine):
    """Pour filtrer une liste : None = toute la copropriété, sinon l'ensemble
    des identifiants de bâtiments autorisés (vide = rien)."""
    ids = set()
    for affectation in utilisateur.affectations.all():
        if action in DROITS[affectation.role].get(domaine, ()):
            if affectation.batiment_id is None:
                return None
            ids.add(affectation.batiment_id)
    return ids


def filtre_documents(utilisateur):
    """Filtre (Q) des documents lisibles, même règle que `peut` : droit de
    lecture, visibilité du rôle et périmètre de bâtiment, affectation par
    affectation."""
    filtre = Q(pk__in=[])
    for affectation in utilisateur.affectations.all():
        if LIRE not in DROITS[affectation.role].get("documents", ()):
            continue
        niveaux = [niveau for niveau, roles in VISIBILITE_DOCUMENTS.items() if affectation.role in roles]
        condition = Q(visibilite__in=niveaux)
        if affectation.batiment_id is not None:
            condition &= Q(batiment__isnull=True) | Q(batiment_id=affectation.batiment_id)
        filtre |= condition
    return filtre
